import uuid
import json
import numpy as np
import cv2
import logging
import os
from app.config import settings
from app.services.model_manager import model_manager
from app.services.model_downloader import model_downloader
from app.services.ai_config_manager import ai_config_manager
from app.services.ticket_parser import parse_ticket_info, extract_text
from app.services.fly_ticket_parser import extract_flight_info

def load_modelscope_model():
    """
    Downloads the Ticket Recognition model from ModelScope.
    Returns the local directory path of the downloaded model.
    """
    try:
        model_dir = os.path.join(settings.MODEL_PATH, 'photo-cls')
        return model_dir
    except Exception as e:
        logging.error(f"Failed to download Ticket Recognition model: {e}")
        raise e

def load_onnx_model():
    """
    Initializes and returns the ONNX model for ticket recognition.
    """
    try:
        import onnxruntime as ort
        logging.info("Initializing ONNX model for Ticket Recognition...")
        
        # Ensure model is downloaded and get path
        model_dir = os.path.join(settings.MODEL_PATH, "photo-cls")
        model_path = os.path.join(model_dir, "ticket-recognition.onnx")
        
        # Initialize ONNX model
        providers = ['CPUExecutionProvider', 'CUDAExecutionProvider']
        session = ort.InferenceSession(model_path, providers=providers)
        
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

class TicketService:
    def __init__(self):
        self._register_downloads()

    def _register_downloads(self):
        def check_model():
            model_path = os.path.join(settings.MODEL_PATH, 'photo-cls', 'ticket-recognition.onnx')
            return os.path.exists(model_path)

        def download_model():
            return load_modelscope_model()

        model_downloader.register_model("tickets_yolo", check_model, download_model)

    def detect(self, image_bytes: bytes):
        """
        执行车票检测与识别
        """
        # Check if model is ready
        # Note: Since load_yolo_model now handles download internally/synchronously if needed,
        # we might not strictly need this check if we relied solely on load_yolo_model.
        # However, keeping it consistent with the model_downloader pattern is good practice.
        if not model_downloader.is_ready("tickets_yolo"):
             # If model_downloader is used, we respect its status.
             # If strictly following the user's synchronous load pattern, this might be redundant but safe.
             # For now, we'll keep it as a fast check.
             if not os.path.exists(os.path.join(settings.MODEL_PATH, 'photo-cls', 'ticket-recognition.onnx')):
                 raise Exception("Ticket recognition model is not ready yet. Please try again later.")

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
            indices = cv2.dnn.NMSBoxes(boxes, scores, 0.25, 0.45)
            filtered_boxes = [boxes[i] for i in indices]
            filtered_scores = [scores[i] for i in indices]
            filtered_class_ids = [class_ids[i] for i in indices]
        else:
            filtered_boxes = []
            filtered_scores = []
            filtered_class_ids = []

        tickets = []

        # 确保输出目录存在 (用于调试或模拟中间文件)
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        if not filtered_boxes:
            return {"tickets": tickets, "count": 0}

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

            # 1. 保存裁剪图像到临时文件
            temp_filename = f"temp_crop_{uuid.uuid4().hex[:8]}_{conf*100:.0f}.png"
            temp_path = os.path.join(output_dir, temp_filename)
            cv2.imwrite(temp_path, crop)

            try:
                # 2. 对裁剪区域执行 OCR (传入文件路径)
                # RapidOCR 支持路径输入
                if not ocr:
                    ocr = model_manager.get_model("ocr")
                out = ocr(temp_path)
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
                
                if cls_name == "label1":
                    # 飞机票
                    info = extract_flight_info(texts)
                    info["type"] = "flight"
                else:
                    # 火车票 (label)
                    info = parse_ticket_info(texts, polys)
                    info["type"] = "train"
                
                logging.info(f"Ticket detection {i} ({cls_name}): parsed info: {info}")
                if info:
                    info['detection_id'] = i
                    tickets.append(info)

            except Exception as e:
                logging.error(f"Error processing JSON flow for ticket {i}: {e}")
            finally:
                # 清理临时 JSON 文件
                if os.path.exists(json_path):
                    os.remove(json_path)

        if filtered_count > 0:
            logging.info(f"Filtered out {filtered_count} low confidence detections")

        return {"tickets": tickets, "count": len(tickets)}

ticket_service = TicketService()
