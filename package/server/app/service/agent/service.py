import asyncio
import logging
from typing import Dict, Any, List
from uuid import UUID
import json
from concurrent.futures import ThreadPoolExecutor
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, trim_messages
from sqlalchemy.orm import Session

from app.core.config_manager import config_manager
from app.db.session import SessionLocal
from app.service.agent.tools import get_agent_tools
from app.crud.agent import get_messages_by_session, create_message
from app.crud import agent as agent_crud
from app.schemas.agent import AgentMessageCreate

logger = logging.getLogger(__name__)

# 全局字典记录被手动终止的 session_id
_aborted_sessions: Dict[str, bool] = {}

def abort_chat_session(session_id: str):
    """
    手动标记某个 session 为终止状态，用于打断仍在运行的流式对话
    """
    _aborted_sessions[session_id] = True

def get_session_history(db: Session, session_id: str) -> List[BaseMessage]:
    db_messages = get_messages_by_session(db, session_id, limit=100)
    messages = []
    for msg in db_messages:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
        elif msg.role == "system":
            messages.append(SystemMessage(content=msg.content))
    return messages

# 滑动窗口大小：传给模型的历史最多保留最近 N 条消息（不按 token 预算，仅按条数）
MAX_HISTORY_MESSAGES = 20

def trim_history_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    基于消息条数的滑动窗口裁剪：保留 system 提示，并只保留最近的 MAX_HISTORY_MESSAGES 条对话。
    使用 token_counter=len 表示"按消息条数计数"，因此这是纯滑动窗口，不涉及 token 预算估算。
    裁剪只影响传给模型的上下文，不影响数据库中的完整历史记录。
    """
    if not messages:
        return messages
    try:
        trimmed = trim_messages(
            messages,
            max_tokens=MAX_HISTORY_MESSAGES,
            strategy="last",
            token_counter=len,  # 按消息条数计数 => 滑动窗口
            include_system=True,
            allow_partial=False,
            start_on="human",
        )
        # 兜底：裁剪结果异常（如空）时回退到原始历史
        return trimmed if trimmed else messages
    except Exception as e:
        logger.warning(f"滑动窗口裁剪失败，回退到完整历史：{e}")
        return messages

# ---- 上下文压缩（摘要 + 近期原文）----
# 历史对话（不含 system）超过该条数时触发压缩，把较早的对话交给 LLM 压成摘要，
# 仅保留最近 KEEP_RECENT_MESSAGES 条原文，避免长对话撑爆上下文且不丢关键信息。
COMPRESSION_TRIGGER = 30
KEEP_RECENT_MESSAGES = 10

_SUMMARY_PROMPT = """你是一个对话摘要器。请把下面这位用户与相册助手的历史对话压缩成简洁的中文摘要，
用于给助手提供长期上下文。要求：
- 保留关键事实：用户提到的人物、地点、时间、偏好、明确的需求或计划；
- 保留对话中出现过的重要 photo_id（如有）；
- 丢弃寒暄、重复内容和无信息量的表述；
- 用要点式（每行一条），控制在 200 字以内，不要输出多余解释。

{prev_summary_section}历史对话：
{conversation}
"""


def _messages_to_text(messages: List[BaseMessage]) -> str:
    """把消息列表转成可读文本，供摘要 LLM 阅读。"""
    lines = []
    for m in messages:
        if isinstance(m, HumanMessage):
            role = "用户"
        elif isinstance(m, AIMessage):
            role = "助手"
        else:
            continue
        content = m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)
        if content:
            lines.append(f"{role}：{content}")
    return "\n".join(lines)


def _get_summary_llm(user_id: str, db: Session):
    """复用用户已配置的分析模型做摘要，返回 llm 或 None。"""
    try:
        user_config = config_manager.get_user_config(user_id, db)
        ai_settings = user_config.ai
        c_id = ai_settings.analysis_connection_id
        m_name = ai_settings.analysis_model_name
        if not c_id or not m_name:
            return None
        connection = next((c for c in ai_settings.connections if c.id == c_id), None)
        if not connection or not connection.enable or not connection.api_key:
            return None
        return ChatOpenAI(
            model=m_name,
            api_key=connection.api_key,
            base_url=connection.api_base if connection.api_base else None,
            temperature=0.2,  # 摘要需稳定
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"初始化摘要模型失败：{e}")
        return None


def compress_history_if_needed(
    messages: List[BaseMessage], user_id: str, session_id: str, db: Session
) -> List[BaseMessage]:
    """
    上下文压缩：当历史对话过长时，把较早的对话压成摘要，只保留最近若干条原文。

    结构：[system(含记忆)] + [历史摘要(SystemMessage)] + [最近 KEEP_RECENT_MESSAGES 条原文]
    - 摘要持久化到 AgentSession.context_summary，后续轮次增量更新，避免每轮重复压缩全部历史；
    - 任何异常都回退到纯滑动窗口 trim_history_messages，保证对话不中断。
    """
    if not messages:
        return messages

    # 拆分 system 与对话体
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    convo = [m for m in messages if not isinstance(m, SystemMessage)]

    # 未达触发阈值，走原有滑动窗口
    if len(convo) <= COMPRESSION_TRIGGER:
        return trim_history_messages(messages)

    try:
        llm = _get_summary_llm(user_id, db)
        if llm is None:
            return trim_history_messages(messages)

        recent = convo[-KEEP_RECENT_MESSAGES:]
        to_compress = convo[:-KEEP_RECENT_MESSAGES]

        prev_summary = agent_crud.get_context_summary(db, session_id)
        prev_summary_section = (
            f"已有的历史摘要（请在此基础上合并更新）：\n{prev_summary}\n\n"
            if prev_summary else ""
        )

        conversation_text = _messages_to_text(to_compress)
        if not conversation_text.strip():
            return trim_history_messages(messages)

        resp = llm.invoke([HumanMessage(content=_SUMMARY_PROMPT.format(
            prev_summary_section=prev_summary_section,
            conversation=conversation_text,
        ))])
        summary_text = (resp.content or "").strip()
        if not summary_text:
            return trim_history_messages(messages)

        # 持久化摘要，供后续轮次复用
        try:
            agent_crud.update_context_summary(db, session_id, summary_text)
        except Exception as e:
            logger.warning(f"持久化上下文摘要失败（不影响本轮）：{e}")

        summary_msg = SystemMessage(content=f"【历史对话摘要】\n{summary_text}")
        return system_msgs + [summary_msg] + recent
    except Exception as e:
        logger.warning(f"上下文压缩失败，回退到滑动窗口：{e}")
        return trim_history_messages(messages)

class FixedChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(self, chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,):
        msg = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        # print('data', chunk)
        # print('msg', msg)
        if msg.message and not msg.message.content:
            message = msg.message
            choices = chunk.get("choices", [])
            for choice in choices:
                delta = choice.get("delta", {})
                if "reasoning" in delta:
                    if not message.content:
                        message.additional_kwargs = {
                            "type": "reasoning",
                            "index": 0,
                            "summary": []
                        }
                    reasoning = delta["reasoning"]
                    message.additional_kwargs['summary'].append(
                        {
                            'index': 0,
                            'type': 'summary_text',
                            'text': reasoning
                        }
                    )
        return msg


class ThinkTagStreamFilter:
    """Split MiniMax-style ``<think>`` content into the reasoning channel."""

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self):
        self.buffer = ""
        self.inside = False

    @staticmethod
    def _prefix_tail(value: str, marker: str) -> int:
        for size in range(min(len(value), len(marker) - 1), 0, -1):
            if marker.startswith(value[-size:]):
                return size
        return 0

    def feed(self, text: str) -> tuple[str, str]:
        self.buffer += text
        visible, reasoning = [], []
        while self.buffer:
            marker = self.CLOSE if self.inside else self.OPEN
            index = self.buffer.find(marker)
            if index >= 0:
                (reasoning if self.inside else visible).append(self.buffer[:index])
                self.buffer = self.buffer[index + len(marker):]
                self.inside = not self.inside
                continue
            keep = self._prefix_tail(self.buffer, marker)
            ready = self.buffer[:-keep] if keep else self.buffer
            (reasoning if self.inside else visible).append(ready)
            self.buffer = self.buffer[-keep:] if keep else ""
            break
        return "".join(visible), "".join(reasoning)

    def flush(self) -> tuple[str, str]:
        result = ("", self.buffer) if self.inside else (self.buffer, "")
        self.buffer = ""
        return result

def get_agent_executor(user_id: str, session_id: str, db: Session, connection_id: str = None, model_name: str = None, user_input: str = None):
    """
    完全适配 langgraph==1.1.3 的 Agent 初始化
    """
    user_config = config_manager.get_user_config(user_id, db)

    ai_settings = user_config.ai

    c_id = connection_id or ai_settings.analysis_connection_id
    m_name = model_name or ai_settings.analysis_model_name

    if not c_id or not m_name:
        raise ValueError("未配置智能分析模型，请在「系统设置 -> AI相关配置」中配置连接和模型。")

    # Find connection
    connection = next((c for c in ai_settings.connections if c.id == c_id), None)
    if not connection:
        raise ValueError(f"未找到指定的 AI 连接配置: {c_id}，请在「系统设置 -> AI相关配置」中检查配置。")

    if not connection.enable:
        raise ValueError(f"选中的 AI 连接已禁用: {c_id}，请在「系统设置 -> AI相关配置」中检查配置")

    if not connection.api_key:
        raise ValueError(f"选中的 AI 连接未配置 API Key: {c_id}，请在「系统设置 -> AI相关配置」中检查配置")

    # 初始化 LLM
    llm = FixedChatOpenAI(
        model=m_name,
        api_key=connection.api_key,
        base_url=connection.api_base if connection.api_base else None,
        timeout=60,
        temperature=0.7,
        streaming=True,
        max_completion_tokens=8192,
        # reasoning_effort='high',

        # use_responses_api=False,
        # reasoning={
        #     "effort": "low",
        #     "summary": "detailed",
        # }
    )

    # 加载工具列表
    tools = get_agent_tools(user_id, session_id=session_id)

    # 获取当前时间
    import datetime
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")

    # 系统提示：通过 PromptTemplate 注入
    system_prompt = f"""你是一个名为 TrailSnap 的智能相册与旅行足迹助手。
今天是 {current_date}。
你的目标是帮助用户回忆他们的旅行、检索相册中的照片，并为他们提供有趣的内容（例如发朋友圈的文案）。在检索照片之前，你必须先根据用户的描述来初步缩小搜索范围，例如日期范围、地点、类型、标签、人物等，如果用户没有提供足够的信息，你可以要求用户进一步给出详细的描述。
你可以使用提供的工具来搜索照片和查看照片的详细数据，例如地址、景区、标签、人脸等。

复杂任务先调用 `list_skills`，再用 `load_skill` 按需加载对应流程。生成旅行日志时必须基于时间线和照片上下文，先用 `create_artifact_draft` 保存可编辑的结构化草稿，再用 `save_artifact_html_page` 为同一作品生成完整的个性化 HTML 页面；严格遵循用户指定的风格和 API 权限，不要臆造工具未确认的经历。
当用户要求创建或整理正式相册时，先加载 `album-organizer`，完成查询和选图后调用 `propose_album_organization`。该工具只创建操作预览，必须明确告诉用户需要在计划卡片中确认；你不能替用户确认，也不能声称尚未确认的修改已经执行。
当用户想用一句话生成旅行相册和旅行日志时，加载 `travel-album`：必要时先用 `discover_trips` 找候选，再完成时间线、代表选图、结构化旅行日志、个性化 HTML 和相册计划。最后把 artifact_id 传给 `propose_album_organization`，让用户一次看到作品和待确认相册；不要把候选旅行直接当成已确认事实。
当用户想检查相册质量、查找未整理照片、缺失元数据、重复照片或异常相册时，加载 `album-doctor` 并调用 `inspect_album_health`。体检是只读的；删除重复文件、修正时间地点等动作没有正式确认工具时，只能给出建议，不能声称已经修复。

【重要指令】：如果你需要展示照片给用户，请必须使用 Markdown 图片语法，并且 URL 格式必须为：
`![照片描述](/api/medias/{user_id}/照片ID/thumbnail)`
例如：
`![美丽的风景](/api/medias/{user_id}/123e4567-e89b-12d3-a456-426614174000/thumbnail)`

当你为用户准备了九宫格照片时，请在回答中直接用上述 Markdown 格式输出这 9 张照片。
绝对不要编造 `img.trail.snap` 等外部或占位图片 URL。若不确定 URL，就只展示作品卡片；照片缩略图 URL 只能由工具返回的真实 photo_id 按上述格式组成。
当用户问“发生了什么事情”或“玩了哪些景点”时，你可以结合照片的描述(description)和一句话旁白(narrative)来丰富你的回答。
请使用友好、自然、有温度的中文与用户交流。
"""

    # 注入长期记忆（仅注入指向有效照片的锚点；传入 user_input 时按语义检索最相关的若干条）
    try:
        from app.service.agent.memory import build_memory_prompt
        memory_prompt = build_memory_prompt(db, user_id, user_input=user_input)
        if memory_prompt:
            system_prompt += memory_prompt
    except Exception as e:
        logger.warning(f"注入长期记忆失败（不影响对话）：{e}")

    # 并通过手动构建 prompt 状态传入
    agent = create_agent(llm, tools)

    return agent, system_prompt

def chat_with_agent(user_id: str, session_id: str, user_input: str, db: Session, connection_id: str = None, model_name: str = None) -> str:
    """
    与 Agent 对话，维护上下文历史
    """
    agent, system_prompt = get_agent_executor(user_id, session_id, db, connection_id, model_name, user_input=user_input)
    messages = get_session_history(db, session_id)
    
    # 将 system_prompt 作为第一条消息传入，如果它不在历史中
    if not messages or not isinstance(messages[0], SystemMessage):
        messages.insert(0, SystemMessage(content=system_prompt))
        
    messages.append(HumanMessage(content=user_input))
    
    # Save user message to DB
    create_message(db, AgentMessageCreate(
        session_id=UUID(session_id),
        role="user",
        content=user_input,
    ))

    # 上下文压缩：历史过长时压成摘要 + 近期原文，否则退化为滑动窗口
    messages = compress_history_if_needed(messages, user_id, session_id, db)
    
    try:
        response = agent.invoke({"messages": messages})
        
        # 获取大模型的回复
        ai_message = response["messages"][-1].content
        reasoning = response["messages"][-1].additional_kwargs.get("reasoning_content")
        tool_calls = response["messages"][-1].tool_calls if hasattr(response["messages"][-1], "tool_calls") else None

        # Save AI message to DB
        create_message(db, AgentMessageCreate(
            session_id=UUID(session_id),
            role="assistant",
            content=ai_message,
            reasoning=reasoning,
            tool_calls=tool_calls
        ))

        # 后台线程异步抽取记忆，不阻塞返回
        if ai_message:
            try:
                from app.service.agent.memory import extract_and_store_memory_task
                tool_calls_for_memory = tool_calls if isinstance(tool_calls, list) else None
                ThreadPoolExecutor(max_workers=1).submit(
                    extract_and_store_memory_task,
                    user_id, user_input, ai_message, tool_calls_for_memory
                )
            except Exception as e:
                logger.warning(f"触发记忆抽取任务失败（不影响对话）：{e}")

        return ai_message
    except Exception as e:
        logger.error(f"Agent 对话失败：{str(e)}", exc_info=True)
        return f"抱歉，处理你的请求时出错了：{str(e)}，请稍后重试。"

def generate_session_title_task(user_id: str, session_id: str, user_input: str):
    try:
        from app.core.config_manager import config_manager
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        from app.crud.agent import get_session, update_session
        from app.schemas.agent import AgentSessionUpdate
        from uuid import UUID

        with SessionLocal() as db:
            if isinstance(user_id, str):
                user_id = UUID(user_id)
            user_config = config_manager.get_user_config(user_id, db)
            
            ai_settings = user_config.ai
            c_id = ai_settings.analysis_connection_id
            m_name = ai_settings.analysis_model_name
            
            if not c_id or not m_name:
                return None
                
            connection = next((c for c in ai_settings.connections if c.id == c_id), None)
            if not connection or not connection.enable or not connection.api_key:
                return None

            llm = ChatOpenAI(
                model=m_name,
                api_key=connection.api_key,
                base_url=connection.api_base if connection.api_base else None,
                temperature=0.7,
                reasoning_effort='none'
            )

            prompt = f"请根据用户的第一个问题，生成一个非常简短的会话标题（不超过10个字）。只返回标题文本，不要包含任何标点符号或其他多余解释。\n用户问题：{user_input}"
            response = llm.invoke([HumanMessage(content=prompt)])
            title = response.content.strip()

            if title.startswith('"') and title.endswith('"'):
                title = title[1:-1]
            if title.startswith("'") and title.endswith("'"):
                title = title[1:-1]

            session = get_session(db, session_id)
            if session:
                update_session(db, session, AgentSessionUpdate(title=title))
                
            return title
    except Exception as e:
        logger.error(f"Failed to generate title: {e}")
        return None

async def stream_chat_with_agent(user_id: str, session_id: str, user_input: str, db: Session, connection_id: str = None, model_name: str = None):
    """
    与 Agent 对话，并使用 SSE 流式返回大模型的回复
    """
    is_saved = False
    full_response = ""
    full_reasoning = ""
    tool_calls_list = []
    artifact_refs = []
    action_plan_refs = []
    think_filter = ThinkTagStreamFilter()
    
    # 标记该会话未被终止
    _aborted_sessions[session_id] = False
    
    try:
        # 在独立的线程中执行可能会阻塞的同步代码，以避免阻塞主事件循环
        agent, system_prompt = await asyncio.to_thread(get_agent_executor, user_id, session_id, db, connection_id, model_name, user_input)
        messages = await asyncio.to_thread(get_session_history, db, session_id)

        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=system_prompt))

        messages.append(HumanMessage(content=user_input))

        # Save user message to DB
        await asyncio.to_thread(create_message, db, AgentMessageCreate(
            session_id=UUID(session_id),
            role="user",
            content=user_input,
        ))
        
        # Check if it's the first message (1 system prompt + 1 user message = 2)
        is_first_message = len(messages) <= 2
        future_title_task = None
        if is_first_message:
            future_title_task = asyncio.create_task(
                asyncio.to_thread(generate_session_title_task, user_id, session_id, user_input)
            )

        # 上下文压缩：历史过长时压成摘要 + 近期原文（在首轮判断之后执行，避免影响标题生成逻辑）
        # 压缩内部可能调用 LLM 生成摘要，放到线程池执行，避免阻塞事件循环
        messages = await asyncio.to_thread(compress_history_if_needed, messages, user_id, session_id, db)

        # 使用 langgraph astream 模式
        async for chunk, metadata in agent.astream({"messages": messages}, stream_mode="messages"):
            if _aborted_sessions.get(session_id, False):
                logger.info(f"Stream manually aborted by API for session {session_id}")
                break

            if chunk.type and (metadata.get("langgraph_node") == "agent" or metadata.get("langgraph_node") == "model"):
                contents = chunk.content
                additional_kwargs = chunk.additional_kwargs
                if isinstance(contents, str):
                    if contents:
                        visible, embedded_reasoning = think_filter.feed(contents)
                        full_response += visible
                        full_reasoning += embedded_reasoning
                        if visible:
                            data = json.dumps({"content": visible, "session_id": session_id})
                            yield f"data: {data}\n\n"
                        if embedded_reasoning:
                            data = json.dumps({"reasoning": embedded_reasoning, "session_id": session_id})
                            yield f"data: {data}\n\n"
                    elif additional_kwargs:
                        summaries = additional_kwargs.get('summary')
                        for summary in summaries:
                            text = summary.get("text", "")
                            full_reasoning += text
                            if text:
                                data = json.dumps({"reasoning": text, "session_id": session_id})
                                yield f"data: {data}\n\n"
                elif isinstance(contents, list):
                    for content in contents:
                        content_type = content.get('type')
                        if content_type == 'text':
                            text = content.get('text','')
                            visible, embedded_reasoning = think_filter.feed(text)
                            full_response += visible
                            full_reasoning += embedded_reasoning
                            # yield SSE data
                            if visible:
                                data = json.dumps({"content": visible, "session_id": session_id})
                                yield f"data: {data}\n\n"
                            if embedded_reasoning:
                                data = json.dumps({"reasoning": embedded_reasoning, "session_id": session_id})
                                yield f"data: {data}\n\n"
                        elif content_type == 'reasoning':
                            summaries = content.get('summary')
                            for summary in summaries:
                                text = summary.get("text", "")
                                full_reasoning += text
                                if text:
                                    data = json.dumps({"reasoning": text, "session_id": session_id})
                                    yield f"data: {data}\n\n"

            # 捕获工具调用
            if metadata.get("langgraph_node") == "tools":
                if hasattr(chunk, "name") and hasattr(chunk, "content") and hasattr(chunk, "tool_call_id"):
                    matching_tool_call = next(
                        (
                            tc
                            for tc in tool_calls_list
                            if tc.get("tool_call_id") == chunk.tool_call_id
                        ),
                        None,
                    )
                    # 部分 OpenAI 兼容模型（例如 MiniMax-M3）返回的
                    # ToolMessage.name 为空，需通过 tool_call_id 找回工具名。
                    tool_name = getattr(chunk, "name", None) or (
                        matching_tool_call.get("tool_name") if matching_tool_call else None
                    )
                    # Record tool return
                    for tc in tool_calls_list:
                        if tc.get("tool_call_id") == chunk.tool_call_id:
                            if isinstance(chunk.content, list):
                                tc["tool_return"] = [block for block in chunk.content if isinstance(block, dict) and block.get("type") == "text"]
                            else:
                                tc["tool_return"] = chunk.content
                            tc["tool_status"] = "success" if not getattr(chunk, "status", "") == "error" else "error"
                    tool_event = {
                        "type": "tool_end", "session_id": session_id,
                        "tool_call_id": chunk.tool_call_id, "tool_name": tool_name,
                        "status": "error" if getattr(chunk, "status", "") == "error" else "success",
                    }
                    yield f"data: {json.dumps(tool_event, ensure_ascii=False)}\n\n"
                    if tool_name in {"create_artifact_draft", "save_artifact_html_page"}:
                        try:
                            parsed = json.loads(chunk.content) if isinstance(chunk.content, str) else chunk.content
                            artifact = parsed.get("artifact") if isinstance(parsed, dict) else None
                            if artifact:
                                artifact_refs.append(artifact)
                                yield f"data: {json.dumps({'type': 'artifact', 'session_id': session_id, 'artifact': artifact}, ensure_ascii=False)}\n\n"
                        except (ValueError, TypeError):
                            logger.warning("无法解析作品工具返回值", exc_info=True)
                    if tool_name == "propose_album_organization":
                        try:
                            parsed = json.loads(chunk.content) if isinstance(chunk.content, str) else chunk.content
                            action_plan = parsed.get("action_plan") if isinstance(parsed, dict) else None
                            if action_plan:
                                action_plan_refs.append(action_plan)
                                yield f"data: {json.dumps({'type': 'action_plan', 'session_id': session_id, 'action_plan': action_plan}, ensure_ascii=False)}\n\n"
                        except (ValueError, TypeError):
                            logger.warning("无法解析 Agent 操作计划返回值", exc_info=True)

            if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                for tc in chunk.tool_calls:
                    if not tc.get("id") or not tc.get("name"):
                        continue
                    # check if already in list
                    if not any(t.get("tool_call_id") == tc.get("id") for t in tool_calls_list):
                        tool_record = {
                            "tool_name": tc.get("name"),
                            "tool_args": tc.get("args"),
                            "tool_call_id": tc.get("id"),
                            "tool_return": None,
                            "tool_status": "pending"
                        }
                        tool_calls_list.append(tool_record)
                        yield f"data: {json.dumps({'type': 'tool_start', 'session_id': session_id, 'tool_call_id': tc.get('id'), 'tool_name': tc.get('name'), 'tool_args': tc.get('args')}, ensure_ascii=False)}\n\n"

        trailing_visible, trailing_reasoning = think_filter.flush()
        if trailing_visible:
            full_response += trailing_visible
            yield f"data: {json.dumps({'content': trailing_visible, 'session_id': session_id})}\n\n"
        if trailing_reasoning:
            full_reasoning += trailing_reasoning
            yield f"data: {json.dumps({'reasoning': trailing_reasoning, 'session_id': session_id})}\n\n"

        if future_title_task:
            try:
                new_title = await asyncio.wait_for(future_title_task, timeout=10.0)
                print(new_title)
                if new_title:
                    data = json.dumps({"title": new_title, "session_id": session_id})
                    yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                logger.error(f"Wait for title generation timeout")
            except Exception as e:
                logger.error(f"Wait for title generation error: {e}")

        # Save AI message to DB
        if full_response or full_reasoning or tool_calls_list:
            await asyncio.to_thread(create_message, db, AgentMessageCreate(
                session_id=UUID(session_id),
                role="assistant",
                content=full_response,
                reasoning=full_reasoning if full_reasoning else None,
                tool_calls=tool_calls_list if tool_calls_list else None,
                content_ext={
                    **({"artifacts": artifact_refs} if artifact_refs else {}),
                    **({"action_plans": action_plan_refs} if action_plan_refs else {}),
                } or None,
            ))
            is_saved = True

            # 异步抽取记忆，不阻塞流式返回
            if full_response and not _aborted_sessions.get(session_id, False):
                try:
                    from app.service.agent.memory import extract_and_store_memory_task
                    asyncio.create_task(
                        asyncio.to_thread(
                            extract_and_store_memory_task,
                            user_id, user_input, full_response, tool_calls_list
                        )
                    )
                except Exception as e:
                    logger.warning(f"触发记忆抽取任务失败（不影响对话）：{e}")

        # 结束标志
        yield "data: [DONE]\n\n"

    except asyncio.CancelledError:
        logger.info(f"Agent chat stream cancelled by client for session {session_id}")
        # The client disconnected, so we shouldn't yield anything more
        raise
    except Exception as e:
        logger.error(f"Agent 流式对话失败：{str(e)}", exc_info=True)
        error_msg = f"\n\n抱歉，处理你的请求时出错了：{str(e)}，请稍后重试。"
        data = json.dumps({"content": error_msg, "session_id": session_id})
        yield f"data: {data}\n\n"

        full_response += error_msg

        yield "data: [DONE]\n\n"

    finally:
        # 兜底保存，处理用户中断（如抛出 GeneratorExit 或 CancelledError）
        # 注意：因为 StreamingResponse 可能会在流结束前导致 FastAPI 关闭 db 会话，
        # 此时如果继续使用原 db 则会抛出 IllegalStateChangeError。
        # 因此，若发生错误或中止，需在此创建一个新的独立 db session 来完成持久化。
        if not is_saved and (full_response or full_reasoning or tool_calls_list):
            try:
                with SessionLocal() as new_db:
                    create_message(new_db, AgentMessageCreate(
                        session_id=UUID(session_id),
                        role="assistant",
                        content=full_response,
                        reasoning=full_reasoning if full_reasoning else None,
                        tool_calls=tool_calls_list if tool_calls_list else None
                    ))
            except Exception as save_err:
                logger.error(f"Failed to save partial message on abort: {save_err}")
            
        # 移除 abort 标记
        _aborted_sessions.pop(session_id, None)
