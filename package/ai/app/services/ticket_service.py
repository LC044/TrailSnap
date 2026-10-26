import uuid
import json
import numpy as np
import cv2
import logging
import os
import re
from app.config import settings
from app.services.model_manager import model_manager
from app.services.unified_model_manager import ai_model_manager
from app.services.ticket_parser import parse_ticket_info, parse_ticket_cards, extract_text, resolve_train_code, normalize_ticket_text, candidate_train_codes
from app.services.fly_ticket_parser import extract_flight_info
from app.services.onnx_providers import create_inference_session
from app.services.ocr_service import openvino_infer_lock

def load_onnx_model():
    """
    Initializes and returns the ONNX model for ticket recognition.
    """
    try:
        logging.info("Initializing ONNX model for Ticket Recognition...")
        
        # Ensure model is downloaded and get path
        if not ai_model_manager.is_ready("tickets_yolo"):
            raise Exception("Ticket model is not ready. 票据识别模型尚未安装，请前往设置中的 AI 模型管理下载。")
        model_dir = str(ai_model_manager.get_model_dir("ticket", task=True))
        model_path = os.path.join(model_dir, "ticket-recognition.onnx")
        
        # Initialize ONNX model
        session = create_inference_session(model_path)
        
        # Set names attribute manually since ONNX model might not have it in the same format
        # We know from the code that class 0 is usually 'label' (train) and class 1 is 'label1' (flight)
        # But we will try to read it from metadata if possible
        names = {0: 'label', 1: 'label1'}
        meta = session.get_modelmeta()
        names_str = meta.custom_metadata_map.get('names', '{}')
        if names_str and names_str != '{}':
            import ast
            try:
                names_dict = ast.literal_eval(names_str)
                names = {int(k): v for k, v in names_dict.items()}
            except Exception:
                pass
                
        # Attach names to session object to simulate YOLO behavior
        session.names = names
        
        logging.info(f"ONNX model initialized successfully.")
        return session
    except Exception as e:
        logging.error(f"Failed to initialize ONNX model: {e}")
        raise e


def release_onnx_model(model):
    del model
    logging.info("ONNX model released")

# 注册 ONNX 模型
model_manager.register_model("tickets_yolo", load_onnx_model, release_onnx_model)

def has_railway_evidence(texts):
    text = ' '.join(texts).translate(str.maketrans({'車': '车', '號': '号'}))
    # Airline numbers (e.g. G3915 as an airline designator) alone are insufficient.
    code = re.search(r'(?<![A-Za-z0-9])[GDCKTZSNLYA]\d{1,4}(?![A-Za-z0-9])', text)
    railway = re.search(r'\d{1,2}\s*车\s*\d{1,3}\s*[A-Fa-f]?\s*号|二等座|一等座|复兴号|中国铁路|12306', text)
    aviation = re.search(r'登机口|航班|航空|机场|经济舱', text)
    return bool(code and railway and not aviation)


def _ocr_blocks(result):
    result = result[0] if isinstance(result, tuple) else result
    if hasattr(result, 'txts'):
        texts = list(result.txts) if result.txts is not None else []
        boxes=getattr(result,'boxes',None)
        polys = boxes.tolist() if hasattr(boxes, 'tolist') else boxes
        return texts, polys if polys is not None else []
    return ([str(item[1]) for item in (result or []) if len(item) >= 2],
            [item[0] for item in (result or []) if len(item) >= 2])


def _full_image_ticket(image, ocr):
    """Detector misses require strong railway evidence, not just a number."""
    with openvino_infer_lock():
        texts, polys = _ocr_blocks(ocr(image,use_det=True,use_cls=True,use_rec=True))
    if not has_railway_evidence(texts):
        return None
    info = parse_ticket_info(texts, polys)
    if not all(info.get(k) for k in ('train_code', 'departure_station', 'arrival_station')):
        return None
    if not re.search(r'\d{1,2}月\d{1,2}日|\d{4}[-/]\d{1,2}[-/]\d{1,2}', info.get('datetime') or ''):
        return None
    return dict(info, type='train', detection_id=0)


def recover_station_line(info,image,texts,polys,ocr):
    """Read an undersized endpoint from its own card's opposite station column."""
    from app.services.ticket_parser import _get_valid_station_names, _poly_center, _is_valid_station_name
    endpoints=('departure_station','arrival_station')
    present=[info[k] for k in endpoints if info.get(k)]
    if len(present)!=1 or not info.get('train_code'):return
    known=_get_valid_station_names()
    anchors=[p for t,p in zip(texts,polys) if t.strip().removesuffix('站')==present[0] and len(p)>=4]
    if len(anchors)!=1:return
    box=anchors[0];x,_=_poly_center(box);height,width=image.shape[:2]
    top=max(0,int(min(p[1] for p in box))-3);bottom=min(height,int(max(p[1] for p in box))+3)
    left,right=(0,int(width*.4)) if x>width/2 else (int(width*.6),width)
    region=image[top:bottom,left:right]
    if region.size==0:return
    enlarged=cv2.resize(region,(region.shape[1]*3,region.shape[0]*3),interpolation=getattr(cv2,'INTER_CUBIC',cv2.INTER_LINEAR))
    try:
        with openvino_infer_lock():
            words,_=_ocr_blocks(ocr(enlarged,use_det=False,use_cls=False))
        candidates=set()
        credible=set()
        for word in words:
            name=re.sub(r'[^\u4e00-\u9fff]','',word).removesuffix('站')
            if name[-1:] in ('过','始','终') and name[:-1] in known:name=name[:-1]
            if name in known and name!=present[0]:candidates.add(name)
            elif _is_valid_station_name(name) and len(name)>=2 and name!=present[0]:credible.add(name)
        if not candidates and len(credible)==1:candidates=credible
        if len(candidates)==1:
            name=candidates.pop()
            info['departure_station'],info['arrival_station']=(name,present[0]) if x>width/2 else (present[0],name)
            info['station_source']='card-line-ocr'
    except Exception:
        logging.warning('Station-line OCR could not recover an endpoint')


def recover_clock_orientation(info,path,texts,ocr):
    clocks=[m for text in texts for m in re.finditer(r'(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)',text)]
    damaged=any(int(m[1])>=24 or int(m[2])>=60 for m in clocks)
    if not info.get('train_code') or (not damaged and _ticket_readability(info)[2]):return
    try:
        with openvino_infer_lock():
            words,boxes=_ocr_blocks(ocr(path,use_det=True,use_cls=False,use_rec=True))
        alternative=parse_ticket_info(words,boxes)
        if alternative.get('train_code')!=info['train_code']:return
        value=alternative.get('datetime') or ''
        match=re.search(r'(\d{1,2}):(\d{2})$',value)
        if not match or int(match[1])>=24 or int(match[2])>=60:return
        if not _ticket_readability(alternative)[2]:return
        info['datetime']=value
        info['datetime_source']='card-without-orientation'
        for key in ('duration_minutes','duration_source'):
            if alternative.get(key):info[key]=alternative[key]
    except Exception:
        logging.warning('Could not recover an incorrectly oriented clock')


def _ticket_readability(info):
    from datetime import datetime
    from app.services.ticket_parser import _get_valid_station_names
    known = _get_valid_station_names()
    endpoints = [info.get(k) for k in ('departure_station', 'arrival_station')]
    date_ok = False
    value = info.get('datetime') or ''
    for text, fmt in ((value, '%Y年%m月%d日 %H:%M'), ('2000年' + value, '%Y年%m月%d日 %H:%M')):
        try:
            date_ok = 1850 <= datetime.strptime(text, fmt).year <= datetime.now().year+2
            if date_ok:
                break
        except ValueError:
            pass
    return (len({n for n in endpoints if n in known}), bool(info.get('train_code')), date_ok)


def recover_mirrored_card(info, image, texts, polys, ocr):
    """Retry unreadable cards after reversing a possible camera/augmentation mirror.

    Accept only a strictly better result with both dictionary endpoints, a service
    and a valid departure datetime. A readable original never incurs this retry.
    """
    if _ticket_readability(info) == (2, True, True):
        return info, texts, polys
    try:
        variants=[('horizontal-mirror',image[:,::-1])]
        if image.shape[0]>image.shape[1]*1.2:
            # A portrait detector crop can be a sideways paper ticket. Text-line
            # angle classification alone does not restore its route geometry.
            variants.extend((label,np.rot90(source,turns))
                            for source,prefix in ((image,''),(image[:,::-1],'mirror-'))
                            for turns,label in ((1,prefix+'rotate-90'),(3,prefix+'rotate-270')))
        for label,variant in variants:
            with openvino_infer_lock():
                words, boxes = _ocr_blocks(ocr(np.ascontiguousarray(variant),
                                              use_det=True, use_cls=True, use_rec=True))
            alternative = parse_ticket_info(words, boxes)
            if _ticket_readability(alternative) == (2, True, True):
                alternative.update(type='train', ocr_transform=label)
                return alternative, words, boxes
    except Exception:
        logging.warning('Could not recover a mirrored ticket card')
    return info, texts, polys


def reconcile_ticket_copies(tickets, serials):
    """Use a readable copy only when the printed ticket serial proves identity."""
    from app.services.ticket_parser import _get_valid_station_names
    known = _get_valid_station_names()
    originals = [dict(t) for t in tickets]
    for info in tickets:
        identity = serials.get(info.get('detection_id'), set())
        if not identity or _ticket_readability(info) == (2, True, True):
            continue
        references=[]
        for other in originals:
            if _ticket_readability(other)!=(2, True, True):continue
            if not identity.intersection(serials.get(other.get('detection_id'),set())):continue
            if info.get('train_code') and info['train_code']!=other['train_code']:continue
            if any(info.get(k) in known and info[k]!=other[k] for k in ('departure_station','arrival_station')):continue
            value=info.get('datetime') or ''
            if value and not other['datetime'].startswith(value):continue
            references.append(other)
        fields=('train_code','departure_station','arrival_station','datetime')
        if references and len({tuple(t[k] for k in fields) for t in references})==1:
            info.update({k:references[0][k] for k in fields})
            info['station_source']='same-printed-ticket-serial'


def supplement_train_code(info, image, ocr):
    """Recover context for a single ticket; never merge fields from multiple cards."""
    try:
        with openvino_infer_lock():
            result = ocr(image,use_det=True,use_cls=True,use_rec=True)
        texts, polys = _ocr_blocks(result)
        texts = [normalize_ticket_text(t) for t in texts]
        code = resolve_train_code(texts, info.get('departure_station', ''), polys)
        if code and not info.get('train_code'):
            info['train_code'] = code
        # More than one service in the full image is ambiguous, even if YOLO
        # found just one card. Departure-specific renumbering is handled above.
        codes = candidate_train_codes(texts)
        if not polys or not all(p is not None and len(p) >= 4 for p in polys):
            return
        full = parse_ticket_info(texts, polys)
        if not codes and re.fullmatch(r'\d{3,5}',full.get('train_code') or ''):
            code=full['train_code']
            codes={code}
            if not info.get('train_code'):info['train_code']=code
        if len(codes) != 1 or not code or code != info.get('train_code'):
            return
        # Existing endpoints must agree before importing a missing endpoint/date.
        endpoints=('departure_station','arrival_station')
        present=[info[k] for k in endpoints if info.get(k)]
        full_pair=[full.get(k) for k in endpoints]
        if len(present)==1 and all(full_pair) and present[0] in full_pair:
            for key in endpoints:info[key]=full[key]
        for key in ('departure_station', 'arrival_station'):
            if info.get(key) and full.get(key) and info[key] != full[key]:
                return
        for key in ('departure_station', 'arrival_station'):
            if not info.get(key) and full.get(key):
                info[key] = full[key]
        if not re.search(r'\d{1,2}月\d{1,2}日|\d{4}[-/]\d{1,2}[-/]\d{1,2}', info.get('datetime') or ''):
            if re.search(r'\d{1,2}月\d{1,2}日|\d{4}[-/]\d{1,2}[-/]\d{1,2}', full.get('datetime') or ''):
                info['datetime'] = full['datetime']
        # Use the card's resolved endpoints to locate its clocks in the page.
        from app.services.ticket_journey_parser import extract_journey_time
        if not info.get('duration_minutes'):
            info.update(extract_journey_time(texts, polys, info))
    except Exception:
        logging.warning('Full-image train-code OCR failed; retaining crop result')


class TicketService:
    def detect(self, image_bytes: bytes):
        """
        执行车票检测与识别
        """
        # Check if model is ready
        # Note: Since load_yolo_model now handles download internally/synchronously if needed,
        # we might not strictly need this check if we relied solely on load_yolo_model.
        if not ai_model_manager.is_ready("tickets_yolo"):
            raise Exception("Ticket model is not ready. 票据识别模型尚未安装，请前往设置中的 AI 模型管理下载。")

        # 获取模型实例
        yolo_session = model_manager.get_model("tickets_yolo")

        # 解码图像
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image data")

        # 查找 'label' (火车票) 和 'label1' (飞机票) 标签的索引
        target_classes = []
        if hasattr(yolo_session, "names"):
            for idx, name in yolo_session.names.items():
                if name == "label" or name == "label1":
                    target_classes.append(idx)

        # ONNX 推理
        input_name = yolo_session.get_inputs()[0].name
        input_shape = yolo_session.get_inputs()[0].shape
        input_size = input_shape[2] if len(input_shape) == 4 and isinstance(input_shape[2], int) else 640

        # Preprocess image
        # Resize maintaining aspect ratio
        h, w = img.shape[:2]
        r = min(input_size / h, input_size / w)
        new_unpad = int(round(w * r)), int(round(h * r))
        dw, dh = input_size - new_unpad[0], input_size - new_unpad[1]
        dw /= 2
        dh /= 2
        
        if img.shape[:2] != new_unpad:
            resized_img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
        else:
            resized_img = img

        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        padded_img = cv2.copyMakeBorder(resized_img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        
        # Convert to CHW and normalize
        blob = padded_img[:, :, ::-1].transpose(2, 0, 1).astype(np.float32)
        blob /= 255.0
        blob = np.expand_dims(blob, axis=0)

        outputs = yolo_session.run(None, {input_name: blob})
        
        # Postprocess outputs (standard YOLOv8 postprocessing)
        predictions = outputs[0]  # shape: (1, 84, 8400) for YOLOv8s
        predictions = np.squeeze(predictions, axis=0)  # shape: (84, 8400)
        predictions = predictions.T  # shape: (8400, 84)
        
        # Filter by confidence and classes
        boxes = []
        scores = []
        class_ids = []
        
        # 0:4 are bbox coordinates (xc, yc, w, h), 4: are class probabilities
        bbox_data = predictions[:, :4]
        class_probs = predictions[:, 4:]
        
        for i in range(predictions.shape[0]):
            cls_id = np.argmax(class_probs[i])
            conf = class_probs[i, cls_id]
            
            if conf > 0.25 and (not target_classes or cls_id in target_classes):
                # Convert xc, yc, w, h to x1, y1, x2, y2
                xc, yc, w_box, h_box = bbox_data[i]
                x1 = xc - w_box / 2
                y1 = yc - h_box / 2
                x2 = xc + w_box / 2
                y2 = yc + h_box / 2
                
                # Scale back to original image
                x1 = (x1 - left) / r
                y1 = (y1 - top) / r
                x2 = (x2 - left) / r
                y2 = (y2 - top) / r
                
                boxes.append([x1, y1, x2, y2])
                scores.append(float(conf))
                class_ids.append(cls_id)
                
        # NMS
        if len(boxes) > 0:
            # OpenCV expects x/y/width/height; detector coordinates are x1/y1/x2/y2.
            nms_boxes = [[x1, y1, x2-x1, y2-y1] for x1, y1, x2, y2 in boxes]
            indices = np.asarray(cv2.dnn.NMSBoxes(nms_boxes, scores, 0.25, 0.45)).reshape(-1)
            filtered_boxes = [boxes[i] for i in indices]
            filtered_scores = [scores[i] for i in indices]
            filtered_class_ids = [class_ids[i] for i in indices]
        else:
            filtered_boxes = []
            filtered_scores = []
            filtered_class_ids = []

        tickets = []
        card_serials = {}

        # 确保输出目录存在 (用于调试或模拟中间文件)
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        if not filtered_boxes:
            try:
                info = _full_image_ticket(img, model_manager.get_model('ocr'))
                if info:
                    tickets.append(info)
            except Exception:
                logging.warning('Full-image fallback could not identify a railway ticket')
            return {"tickets": tickets, "count": len(tickets)}

        ocr = None
        filtered_count = 0

        for i, box in enumerate(filtered_boxes):
            conf = filtered_scores[i]
            cls_id = filtered_class_ids[i]
            
            x1, y1, x2, y2 = map(int, box)

            # 边界保护
            h_orig, w_orig = img.shape[:2]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w_orig, x2)
            y2 = min(h_orig, y2)

            # 裁剪车票区域
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            # Small cards in contact sheets/crops otherwise fall below the text
            # detector's useful scale. Resize pixels only; never synthesize text.
            ch,cw=crop.shape[:2]
            scale=min(4.0,max(1.0,640/cw,192/ch))
            if scale>1:
                crop=cv2.resize(crop,(round(cw*scale),round(ch*scale)),interpolation=cv2.INTER_CUBIC)

            # 1. 保存裁剪图像到临时文件
            temp_filename = f"temp_crop_{uuid.uuid4().hex[:8]}_{conf*100:.0f}.png"
            temp_path = os.path.join(output_dir, temp_filename)
            cv2.imwrite(temp_path, crop)

            try:
                # 2. 对裁剪区域执行 OCR (传入文件路径)
                # RapidOCR 支持路径输入
                # 共享 ocr_service 的 RapidOCR 实例；OpenVINO 后端下 InferRequest 非线程
                # 安全，需通过 openvino_infer_lock() 与 ocr_service.detect_text 互斥，避免
                # 并发请求（或与 /ocr/predict 同时调用）时抛 "Infer Request is busy"。
                if not ocr:
                    ocr = model_manager.get_model("ocr")
                with openvino_infer_lock():
                    out = ocr(temp_path,use_det=True,use_cls=True,use_rec=True)
            except Exception as e:
                logging.warning(f"OCR inference failed for {temp_path}: {e}")
                out = None
            finally:
                pass

            if isinstance(out, tuple):
                ocr_result = out[0]
            else:
                ocr_result = out
            
            # 构造 JSON 数据结构以模拟 yolo_ocr.py 的中间结果
            json_data = {"rec_texts": [], "rec_polys": []}
            if ocr_result:
                try:
                    # Check for RapidOCROutput object (has txts, boxes, scores attributes)
                    if hasattr(ocr_result, 'txts') and hasattr(ocr_result, 'boxes'):
                        # Handle RapidOCROutput object
                        txts = ocr_result.txts
                        boxes_ocr = ocr_result.boxes
                        for j in range(len(txts)):
                            text = txts[j]
                            # Convert numpy array box to list for JSON serialization
                            poly = boxes_ocr[j].tolist() if hasattr(boxes_ocr[j], 'tolist') else boxes_ocr[j]
                            json_data["rec_texts"].append(str(text))
                            json_data["rec_polys"].append(poly)
                    else:
                        # Handle standard list of tuples/lists
                        for item in ocr_result:
                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                poly = item[0]
                                text = item[1]
                                json_data["rec_texts"].append(str(text))
                                json_data["rec_polys"].append(poly)
                except Exception as e:
                     logging.warning(f"OCR result parse failed: {e}")

            # 3. 保存原始OCR结果到JSON (完全对齐 yolo_ocr.py 流程)
            json_filename = f"temp_crop_{uuid.uuid4().hex[:8]}_ocr.json"
            json_path = os.path.join(output_dir, json_filename)
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                
                # 4. 从JSON文件中提取文本 (调用 ticket_parser_adapter 中的 extract_text)
                texts, polys = extract_text(json_path)
                
                # 5. 解析车票信息
                cls_name = yolo_session.names.get(cls_id, str(cls_id))
                additional=[]
                
                if cls_name == "label1" and not has_railway_evidence(texts):
                    # 飞机票
                    info = extract_flight_info(texts)
                    info["type"] = "flight"
                    # Advertisements/order headers can look like boarding passes.
                    # A detector box alone is not evidence of an airline ticket.
                    if not info.get('flight_code') and not re.search(r'航班|航空|登机|机场', ' '.join(texts)):
                        continue
                else:
                    # 火车票 (label)
                    info = parse_ticket_info(texts, polys)
                    info["type"] = "train"
                    if not info.get('train_code') or not (info.get('departure_station') and info.get('arrival_station')):
                        cards=parse_ticket_cards(texts,polys,initial=info)
                        info=cards[0]
                        info['type']='train'
                        additional=cards[1:]
                    if not additional:
                        info, texts, polys = recover_mirrored_card(info,crop,texts,polys,ocr)
                        recover_station_line(info,crop,texts,polys,ocr)
                        recover_clock_orientation(info,temp_path,texts,ocr)
                    card_serials[i]={m[0]+m[1:].replace('O','0') for text in texts
                                     for m in re.findall(r'[A-Z][0-9O]{6,8}(?![0-9])',text.upper())}
                
                logging.info(f"Ticket detection {i} ({cls_name}): parsed info: {info}")
                if info:
                    info['detection_id'] = i
                    tickets.append(info)
                    for extra in additional:
                        tickets.append(dict(extra,type='train',detection_id=i))

            except Exception as e:
                logging.error(f"Error processing JSON flow for ticket {i}: {e}")
            finally:
                # 清理临时 JSON 文件
                if os.path.exists(json_path):
                    os.remove(json_path)
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        if filtered_count > 0:
            logging.info(f"Filtered out {filtered_count} low confidence detections")

        reconcile_ticket_copies(tickets,card_serials)

        if len(tickets) == 1 and tickets[0].get('type') == 'train':
            info = tickets[0]
            missing_fields = any(not info.get(k) for k in ('train_code', 'departure_station', 'arrival_station'))
            missing_date = not re.search(r'\d{1,2}月\d{1,2}日|\d{4}[-/]\d{1,2}[-/]\d{1,2}', info.get('datetime') or '')
            if missing_fields or missing_date:
                supplement_train_code(info, img, ocr)
        elif len(tickets) > 1 and all(t.get('type') == 'train' for t in tickets):
            if any(re.fullmatch(r'\d{1,2}:\d{2}',t.get('datetime') or '') for t in tickets):
                try:
                    with openvino_infer_lock():
                        texts, context_polys = _ocr_blocks(ocr(img,use_det=True,use_cls=True,use_rec=True))
                    from app.services.ticket_journey_parser import apply_shared_ticket_date,apply_section_ticket_dates
                    apply_shared_ticket_date(texts,tickets)
                    apply_section_ticket_dates(texts,context_polys,tickets)
                except Exception:
                    logging.warning('Could not recover a shared ticket-page date')

        return {"tickets": tickets, "count": len(tickets)}

ticket_service = TicketService()
