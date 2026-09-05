<template>
  <div v-if="modelValue" :class="['agent-chat-overlay', { 'is-fullscreen': isFullscreen }]" @click.self="handleClose">
    <div :class="['agent-chat-container', { 'is-fullscreen': isFullscreen, 'has-sidebar': isSidebarOpen }]">
      
      <!-- 移动端侧边栏遮罩：侧边栏以 absolute 抽屉展开时遮住主区域，点击空白处关闭 -->
      <div v-if="isSidebarOpen" class="agent-sidebar-backdrop sm:hidden" @click="isSidebarOpen = false"></div>

      <!-- Sidebar for Sessions -->
      <AgentSidebar
        :is-open="isSidebarOpen"
        :sessions="sessions"
        :current-session-id="currentSession?.id"
        @create="createNewSession"
        @close="isSidebarOpen = false"
        @switch="switchSession"
        @command="handleSessionCommand"
      />

      <!-- Main Chat Area -->
      <div class="agent-main">
        <!-- Header -->
        <AgentHeader
          :is-fullscreen="isFullscreen"
          :is-selection-mode="isSelectionMode"
          :selected-count="selectedMessages.length"
          :available-models="availableModels"
          v-model="selectedModelValue"
          :is-models-loading="isModelsLoading"
          @toggle-sidebar="isSidebarOpen = !isSidebarOpen"
          @toggle-fullscreen="isFullscreen = !isFullscreen"
          @close="handleClose"
          @cancel-selection="isSelectionMode = false"
          @delete-selection="deleteSelectedMessages"
        />

        <!-- Messages -->
        <div class="agent-chat-messages" ref="messagesContainer">
          <div class="w-full max-w-4xl mx-auto flex flex-col space-y-6 pb-2">
            <AgentMessageItem
              v-for="(msg, index) in messages"
              :key="msg.id || index"
              :msg="msg"
              :index="index"
              :is-selection-mode="isSelectionMode"
              :is-selected="selectedMessages.includes(msg.id!)"
              :is-last-assistant="isLastAssistantMessage(index)"
              :is-last-user="isLastUserMessage(index)"
              :is-dropdown-active="activeDropdownIndex === index"
              :render-markdown="renderMarkdown"
              @toggle-select="toggleSelectMessage"
              @copy="copyMessage"
              @regenerate="handleRegenerate"
              @edit="handleEditMessage"
              @command="handleMessageCommand"
              @dropdown-visible="handleDropdownVisibleChange"
              @toggle-reasoning="msg.isReasoningExpanded = !msg.isReasoningExpanded"
            />

            <div v-if="isLoading" class="message-wrapper justify-start">
              <div class="message-avatar assistant">
                <Bot class="w-4 h-4" />
              </div>
              <div class="message-bubble assistant flex items-center gap-2 py-3">
                <Loader2 class="w-4 h-4 animate-spin text-indigo-500" />
                <span class="text-sm text-slate-500">思考中...</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Input Area -->
        <AgentInput
          v-model="inputMessage"
          :is-generating="isGenerating"
          :is-selection-mode="isSelectionMode"
          @send="sendMessage"
          @abort="handleAbort"
        />
      </div>
    </div>

    <!-- 引入全屏图片预览组件 -->
    <PhotoLightbox
      :visible="isLightboxOpen"
      :image="currentPhotoSrc"
      :hasPrev="currentPhotoIndex > 0"
      :hasNext="currentPhotoIndex < allPhotos.length - 1"
      @close="isLightboxOpen = false"
      @prev="() => { if (currentPhotoIndex > 0) { currentPhotoIndex--; currentPhotoSrc = allPhotos[currentPhotoIndex]; } }"
      @next="() => { if (currentPhotoIndex < allPhotos.length - 1) { currentPhotoIndex++; currentPhotoSrc = allPhotos[currentPhotoIndex]; } }"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loader2, Bot } from 'lucide-vue-next';
import { agentApi, type AgentSession, type AgentMessage, type ToolProgressEvent, type AgentArtifactRef, type AgentActionPlan } from '@/api/agent';
import { settingsApi } from '@/api/settings';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import PhotoLightbox from '@/components/PhotoLightbox.vue';

import AgentSidebar from './components/AgentSidebar.vue';
import AgentHeader from './components/AgentHeader.vue';
import AgentMessageItem from './components/AgentMessageItem.vue';
import AgentInput from './components/AgentInput.vue';
import { photoIdFromMediaUrl, thumbnailToFileUrl, thumbnailUrl } from '@/utils/mediaUrl';
import { useUiStore } from '@/stores/uiStore';

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();
const uiStore = useUiStore();

// Lightbox 状态
const isLightboxOpen = ref(false);
const currentPhotoSrc = ref<any>(null);
const currentPhotoIndex = ref(0);
const allPhotos = ref<any[]>([]);

// Layout & UI 状态
const isFullscreen = ref(false);
const isSidebarOpen = ref(false);

// Models & Connections state
const availableModels = ref<Array<{ conn_id: string, model: string, label: string }>>([]);
const selectedModelValue = ref('');
const isModelsLoading = ref(false);

const loadModels = async () => {
  isModelsLoading.value = true;
  try {
    const res = await settingsApi.getModels();
    const list: Array<{ conn_id: string, model: string, label: string }> = [];
    if (res && res.connections) {
      res.connections.forEach((conn: any) => {
        if (conn.models && conn.models.length > 0) {
          conn.models.forEach((m: string) => {
            list.push({
              conn_id: conn.id,
              model: m,
              label: `${m} (${conn.api_base || conn.id})`
            });
          });
        }
      });
    }
    availableModels.value = list;
    if (res.chat_connection_id && res.chat_model_name) {
      selectedModelValue.value = `${res.chat_connection_id}|${res.chat_model_name}`;
    } else if (res.analysis_connection_id && res.analysis_model_name) {
      selectedModelValue.value = `${res.analysis_connection_id}|${res.analysis_model_name}`;
    } else if (list.length > 0) {
      selectedModelValue.value = `${list[0].conn_id}|${list[0].model}`;
    }
  } catch (e) {
    console.error('Failed to load models', e);
  } finally {
    isModelsLoading.value = false;
  }
};

// 会话管理
const sessions = ref<AgentSession[]>([]);
const currentSession = ref<AgentSession | null>(null);

// 消息管理
export interface MessageItem {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  isMarkdown?: boolean;
  reasoning?: string;
  isReasoningExpanded?: boolean;
  toolEvents?: ToolProgressEvent[];
  artifacts?: AgentArtifactRef[];
  actionPlans?: AgentActionPlan[];
}

const activeDropdownIndex = ref<number | null>(null);

const handleDropdownVisibleChange = (visible: boolean, index: number) => {
  if (visible) {
    activeDropdownIndex.value = index;
  } else {
    if (activeDropdownIndex.value === index) {
      activeDropdownIndex.value = null;
    }
  }
};

const defaultWelcomeMessage: MessageItem = {
  role: 'assistant',
  content: '你好！我是 TrailSnap 智能相册助手。你可以问我：\n- "帮我整理一下最近拍的照片，写一段朋友圈文案"\n- "今年国庆节去了哪些地方？"\n- "找几张在海边的照片"',
  isMarkdown: false
};

const messages = ref<MessageItem[]>([ { ...defaultWelcomeMessage } ]);
const inputMessage = ref('');
const isLoading = ref(false);
const isGenerating = ref(false);

watch(
  () => [props.modelValue, uiStore.pendingAgentPrompt, isGenerating.value] as const,
  ([open, pending, generating]) => {
    if (!open || !pending || generating) return;
    const request = uiStore.consumeAgentPrompt();
    inputMessage.value = request.prompt;
    nextTick(() => {
      if (request.autoSend) sendMessage();
      else ElMessage.info('风格需求已填入，发送后 Agent 会生成个性化页面');
    });
  },
  { immediate: true }
);
const messagesContainer = ref<HTMLElement | null>(null);
const abortController = ref<AbortController | null>(null);
const runningSessionId = ref<string | null>(null);

const handleAbort = async () => {
  if (runningSessionId.value) {
    try {
      await agentApi.abortChat(runningSessionId.value);
    } catch (e) {
      console.error('Failed to send abort signal to backend', e);
    }
  }

  if (abortController.value) {
    abortController.value.abort();
    abortController.value = null;
    isLoading.value = false;
    isGenerating.value = false;
  }
};

// 批量选择
const isSelectionMode = ref(false);
const selectedMessages = ref<number[]>([]);

const toggleSelectMessage = (id?: number) => {
  if (id === undefined) return;
  const index = selectedMessages.value.indexOf(id);
  if (index > -1) {
    selectedMessages.value.splice(index, 1);
  } else {
    selectedMessages.value.push(id);
  }
};

const deleteSelectedMessages = async () => {
  if (selectedMessages.value.length === 0 || !currentSession.value) return;
  
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedMessages.value.length} 条消息吗？`, '提示', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    });
    
    await agentApi.deleteMessages(currentSession.value.id, selectedMessages.value);
    ElMessage.success('删除成功');
    isSelectionMode.value = false;
    selectedMessages.value = [];
    await loadMessages(currentSession.value.id);
  } catch (e) {
    // cancelled or error
  }
};

// 消息操作功能
const copyMessage = async (content: string) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(content);
      ElMessage.success('已复制到剪贴板');
    } else {
      const textArea = document.createElement("textarea");
      textArea.value = content;
      textArea.style.position = "fixed";
      textArea.style.left = "-999999px";
      textArea.style.top = "-999999px";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        document.execCommand('copy');
        ElMessage.success('已复制到剪贴板');
      } catch (err) {
        ElMessage.error('复制失败');
      } finally {
        textArea.remove();
      }
    }
  } catch (err) {
    ElMessage.error('复制失败');
  }
};

const handleMessageCommand = (command: string, msg: MessageItem, index: number) => {
  if (command === 'delete') {
    isSelectionMode.value = true;
    selectedMessages.value = [];
    
    if (msg.id !== undefined) {
      selectedMessages.value.push(msg.id);
    }
    
    if (msg.role === 'assistant' && index > 0) {
      const prevMsg = messages.value[index - 1];
      if (prevMsg.role === 'user' && prevMsg.id !== undefined) {
        selectedMessages.value.push(prevMsg.id);
      }
    } else if (msg.role === 'user' && index < messages.value.length - 1) {
      const nextMsg = messages.value[index + 1];
      if (nextMsg.role === 'assistant' && nextMsg.id !== undefined) {
        selectedMessages.value.push(nextMsg.id);
      }
    }
  }
};

const isLastAssistantMessage = (index: number) => {
  return index === messages.value.length - 1;
};

const isLastUserMessage = (index: number) => {
  if (index === messages.value.length - 1) return true;
  if (index === messages.value.length - 2 && messages.value[index + 1].role === 'assistant') return true;
  return false;
};

const handleRegenerate = async (msg: MessageItem, index: number) => {
  if (index === 0) return;
  const prevMsg = messages.value[index - 1];
  if (prevMsg.role !== 'user') return;
  
  const userText = prevMsg.content;
  const idsToDelete = [];
  if (msg.id !== undefined) idsToDelete.push(msg.id);
  if (prevMsg.id !== undefined) idsToDelete.push(prevMsg.id);
  
  if (idsToDelete.length > 0 && currentSession.value) {
    try {
      await agentApi.deleteMessages(currentSession.value.id, idsToDelete);
    } catch (e) {
      ElMessage.error('重新生成失败');
      return;
    }
  }
  
  messages.value.splice(index - 1, 2);
  inputMessage.value = userText;
  await sendMessage();
};

const handleEditMessage = async (msg: MessageItem, index: number) => {
  try {
    const { value } = await ElMessageBox.prompt('编辑消息', '编辑', {
      confirmButtonText: '重新发送',
      cancelButtonText: '取消',
      inputValue: msg.content,
      inputType: 'textarea',
      customStyle: { maxWidth: '90vw' }
    });
    
    if (value && value.trim() !== '' && value.trim() !== msg.content) {
      const idsToDelete = [];
      if (msg.id !== undefined) idsToDelete.push(msg.id);
      
      let deleteCount = 1;
      if (index < messages.value.length - 1) {
        const nextMsg = messages.value[index + 1];
        if (nextMsg.role === 'assistant' && nextMsg.id !== undefined) {
          idsToDelete.push(nextMsg.id);
          deleteCount = 2;
        }
      }
      
      if (idsToDelete.length > 0 && currentSession.value) {
        await agentApi.deleteMessages(currentSession.value.id, idsToDelete);
      }
      
      messages.value.splice(index, deleteCount);
      inputMessage.value = value.trim();
      await sendMessage();
    }
  } catch (e) {
    // cancelled
  }
};

// Markdown 解析器配置
const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
});

md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const originalSrc = token.attrGet('src') || '';
  const alt = token.content || '';
  const photoId = photoIdFromMediaUrl(originalSrc);
  // Agent 图片只允许指向可验证的 TrailSnap photo_id。即使模型把媒体路径
  // 套在外部域名上，也重新规范化为当前 Server 地址，绝不请求该外部域名。
  if (!photoId) return '';
  const src = thumbnailUrl(photoId);

  const fullSrc = thumbnailToFileUrl(src);

  return `<agent-image data-src="${src}?size=medium" data-full-src="${fullSrc}" data-alt="${alt}"></agent-image>`;
};

const defaultRender = md.renderer.rules.paragraph_open || function(tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.paragraph_open = function(tokens, idx, options, env, self) {
  return defaultRender(tokens, idx, options, env, self);
};

const defaultParagraphClose = md.renderer.rules.paragraph_close || function(tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.paragraph_close = function(tokens, idx, options, env, self) {
  return defaultParagraphClose(tokens, idx, options, env, self);
};

const scrollToBottom = async (force: boolean = false) => {
  await nextTick();
  if (messagesContainer.value) {
    const { scrollTop, scrollHeight, clientHeight } = messagesContainer.value;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
    if (force || isNearBottom) {
      messagesContainer.value.scrollTop = scrollHeight;
    }
  }
};

const handleClose = () => {
  emit('update:modelValue', false);
};

const renderMarkdown = (content: string, fallbackPhotoIds: string[] = []) => {
  let fallbackIndex = 0;
  // 模型偶尔会把照片路径套在外部或占位域名上。提取可验证的 photo_id 后
  // 重写为本地路径；无法验证时用作品来源照片兜底，否则直接移除。
  const safeContent = content.replace(/!\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/gi, (_match, alt, url) => {
    const embeddedPhotoId = photoIdFromMediaUrl(url);
    const photoId = embeddedPhotoId || fallbackPhotoIds[fallbackIndex++];
    return photoId ? `![${alt}](/api/medias/${photoId}/thumbnail)` : '';
  });
  let rawHtml = md.render(safeContent);

  // 合并「连续的、仅包含图片的 <p> 段落」为九宫格网格。
  // markdown 会把图片间有空行的多张图解析成多个相邻 <p>，这里把这些相邻的纯图片段落
  // （彼此间只有空白）整体识别，统一渲染成 grid，从而支持 AI/主动消息逐行输出图片的场景。
  const imageParagraphs = /(?:<p>(?:\s*<agent-image[^>]*><\/agent-image>\s*)+<\/p>\s*)+/g;
  rawHtml = rawHtml.replace(imageParagraphs, (block) => {
    const items: string[] = [];
    const single = /<agent-image data-src="([^"]+)" data-full-src="([^"]+)" data-alt="([^"]*)"><\/agent-image>/g;
    let m: RegExpExecArray | null;
    while ((m = single.exec(block)) !== null) {
      items.push(
        `<div class="agent-gallery-item"><img src="${m[1]}" alt="${m[3]}" class="agent-gallery-image" data-full-src="${m[2]}" /></div>`
      );
    }
    // 单张图片不组成网格，保持原有的行内小图展示
    if (items.length <= 1) return block;
    return `<div class="agent-gallery-grid">${items.join('')}</div>`;
  });

  rawHtml = rawHtml.replace(/<agent-image data-src="([^"]+)" data-full-src="([^"]+)" data-alt="([^"]*)"><\/agent-image>/g, 
      '<img src="$1" alt="$3" class="agent-gallery-image inline-image max-h-[200px]" data-full-src="$2" />'
  );

  rawHtml = rawHtml.replace(/<p>\s*<\/p>/g, '');

  return DOMPurify.sanitize(rawHtml, { 
    ADD_TAGS: ['img', 'div'], 
    ADD_ATTR: ['target', 'class', 'src', 'alt', 'data-full-src'] 
  });
};

const setupImageClick = () => {
  if (messagesContainer.value) {
    const images = messagesContainer.value.querySelectorAll('.agent-gallery-image');
    images.forEach(img => {
      const clone = img.cloneNode(true);
      if(img.parentNode) {
        img.parentNode.replaceChild(clone, img);
      }
      clone.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const target = e.target as HTMLImageElement;
        
        let originalSrc = target.getAttribute('data-full-src') || thumbnailToFileUrl(target.src);
        
        const imgElements = messagesContainer.value?.querySelectorAll('.agent-gallery-image');
        if (imgElements && imgElements.length > 0) {
          allPhotos.value = Array.from(imgElements).map((el, index) => {
            let photoSrc = el.getAttribute('data-full-src') || thumbnailToFileUrl((el as HTMLImageElement).src);
            
            let realId = `agent-img-${index}`;
            realId = photoIdFromMediaUrl(photoSrc) || realId;
            
            if (!photoSrc.startsWith('http') && !photoSrc.startsWith('data:')) {
               photoSrc = window.location.origin + (photoSrc.startsWith('/') ? photoSrc : '/' + photoSrc);
            }

            if (!photoSrc.includes('/thumbnail') && !photoSrc.includes('/file')) {
                const match = photoSrc.match(/(\/medias\/[a-f0-9\-]{36})$/i);
                if (match) {
                    photoSrc = photoSrc + '/file';
                }
            }

            return { 
              id: realId, 
              url: photoSrc, 
              preview: photoSrc, 
              file_type: 'image' 
            };
          });
          const clickedIndex = Array.from(imgElements).indexOf(target);
          currentPhotoIndex.value = clickedIndex !== -1 ? clickedIndex : 0;
          currentPhotoSrc.value = allPhotos.value[currentPhotoIndex.value];
          isLightboxOpen.value = true;
        } else {
          let fallbackSrc = originalSrc;
          let realId = 'agent-img-0';
          realId = photoIdFromMediaUrl(fallbackSrc) || realId;
          if (!fallbackSrc.startsWith('http') && !fallbackSrc.startsWith('data:')) {
             fallbackSrc = window.location.origin + (fallbackSrc.startsWith('/') ? fallbackSrc : '/' + fallbackSrc);
          }
          
          if (!fallbackSrc.includes('/thumbnail') && !fallbackSrc.includes('/file')) {
              const match = fallbackSrc.match(/(\/medias\/[a-f0-9\-]{36})$/i);
              if (match) {
                  fallbackSrc = fallbackSrc + '/file';
              }
          }
          
          const singleImg = { id: realId, url: fallbackSrc, preview: fallbackSrc, file_type: 'image' };
          allPhotos.value = [singleImg];
          currentPhotoIndex.value = 0;
          currentPhotoSrc.value = singleImg;
          isLightboxOpen.value = true;
        }
      });
    });
  }
};

// API 交互逻辑
const loadSessions = async () => {
  try {
    const res = await agentApi.getSessions();
    sessions.value = res.data;
  } catch (error) {
    console.error('Failed to load sessions', error);
  }
};

// 主动式记忆：打开助手时拉取未读的主动消息，作为助手消息置顶展示，并标记已读
const loadProactiveMessages = async () => {
  try {
    const res: any = await agentApi.getProactiveMessages();
    const list = res?.data?.messages ?? [];
    if (!list.length) return;
    const proactiveItems: MessageItem[] = list.map((m: any) => ({
      id: m.id,
      role: 'assistant' as const,
      content: m.content,
      isMarkdown: true,
    }));
    // 置顶插入到欢迎语之后
    messages.value.splice(1, 0, ...proactiveItems);
    scrollToBottom(true);
    // 标记已读，消除红点
    for (const m of list) {
      agentApi.markProactiveRead(m.id).catch(() => {});
    }
  } catch (e) {
    // 静默失败，不影响正常对话
  }
};

const createNewSession = () => {
  currentSession.value = null;
  messages.value = [ { ...defaultWelcomeMessage } ];
  isSelectionMode.value = false;
  selectedMessages.value = [];
  if (window.innerWidth < 640) {
    isSidebarOpen.value = false;
  }
};

const switchSession = async (session: AgentSession) => {
  if (currentSession.value?.id === session.id) return;
  currentSession.value = session;
  isSelectionMode.value = false;
  selectedMessages.value = [];
  await loadMessages(session.id);
  if (window.innerWidth < 640) {
    isSidebarOpen.value = false;
  }
};

const loadMessages = async (sessionId: string, showLoading: boolean = true) => {
  if (showLoading) isLoading.value = true;
  try {
    const res = await agentApi.getSessionMessages(sessionId);
    if (res.data.length === 0) {
      messages.value = [ { ...defaultWelcomeMessage } ];
    } else {
      messages.value = res.data.map(m => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        isMarkdown: m.role === 'assistant',
        reasoning: m.reasoning || undefined,
        isReasoningExpanded: false,
        toolEvents: (m.tool_calls || []).map((tool: any) => ({ type: 'tool_end', tool_call_id: tool.tool_call_id, tool_name: tool.tool_name, status: tool.tool_status === 'error' ? 'error' : 'success' })),
        artifacts: m.content_ext?.artifacts || [],
        actionPlans: m.content_ext?.action_plans || []
      }));
    }
    await scrollToBottom(true);
    setTimeout(setupImageClick, 100);
  } catch (error) {
    ElMessage.error('加载消息失败');
  } finally {
    if (showLoading) isLoading.value = false;
  }
};

const deleteSession = async (sessionId: string) => {
  try {
    await ElMessageBox.confirm('确定删除该会话吗？', '提示', { type: 'warning' });
    await agentApi.deleteSession(sessionId);
    ElMessage.success('删除成功');
    if (currentSession.value?.id === sessionId) {
      createNewSession();
    }
    await loadSessions();
  } catch (e) {
    // cancelled
  }
};

const togglePin = async (session: AgentSession) => {
  try {
    await agentApi.pinSession(session.id, !session.is_pinned);
    await loadSessions();
  } catch (error) {
    ElMessage.error('操作失败');
  }
};

const handleSessionCommand = (command: string, session: AgentSession) => {
  if (command === 'pin') {
    togglePin(session);
  } else if (command === 'delete') {
    deleteSession(session.id);
  }
};

const sendMessage = async () => {
  if (!inputMessage.value.trim() || isGenerating.value) return;

  const userText = inputMessage.value.trim();
  messages.value.push({ role: 'user', content: userText });
  inputMessage.value = '';
  isLoading.value = true;
  isGenerating.value = true;
  await scrollToBottom(true);

  abortController.value = new AbortController();
  runningSessionId.value = currentSession.value?.id || null;

  try {
    let aiMessageIndex = -1;
    let sessionIdReceived = false;

    const [conn_id, model] = selectedModelValue.value.split('|');

    await agentApi.chatStream(
      {
        message: userText,
        session_id: currentSession.value?.id || undefined,
        connection_id: conn_id || undefined,
        model_name: model || undefined
      },
      (content) => {
        if (aiMessageIndex === -1) {
          isLoading.value = false;
          aiMessageIndex = messages.value.length;
          messages.value.push({ role: 'assistant', content: content, isMarkdown: true, reasoning: '', isReasoningExpanded: true });
        } else {
          messages.value[aiMessageIndex].content += content;
          if (messages.value[aiMessageIndex].isReasoningExpanded && messages.value[aiMessageIndex].content.trim()) {
            messages.value[aiMessageIndex].isReasoningExpanded = false;
          }
        }
        scrollToBottom();
      },
      async (sessionId) => {
        runningSessionId.value = sessionId;
        if (!sessionIdReceived && (!currentSession.value || currentSession.value.id !== sessionId)) {
          sessionIdReceived = true;
          await loadSessions();
          const newSession = sessions.value.find(s => s.id === sessionId);
          if (newSession) {
            currentSession.value = newSession;
          }
        }
      },
      (title) => {
        if (currentSession.value) {
          currentSession.value.title = title;
        }
        const sessionInList = sessions.value.find(s => s.id === currentSession.value?.id);
        if (sessionInList) {
          sessionInList.title = title;
        }
      },
      (reasoningContent) => {
        if (aiMessageIndex === -1) {
          isLoading.value = false;
          aiMessageIndex = messages.value.length;
          messages.value.push({ role: 'assistant', content: '', isMarkdown: true, reasoning: reasoningContent, isReasoningExpanded: true });
        } else {
          if (messages.value[aiMessageIndex].reasoning === undefined) {
            messages.value[aiMessageIndex].reasoning = reasoningContent;
            messages.value[aiMessageIndex].isReasoningExpanded = true;
          } else {
            messages.value[aiMessageIndex].reasoning += reasoningContent;
          }
        }
        scrollToBottom();
      },
      abortController.value.signal,
      (event) => {
        if (aiMessageIndex === -1) {
          isLoading.value = false;
          aiMessageIndex = messages.value.length;
          messages.value.push({ role: 'assistant', content: '', isMarkdown: true, reasoning: '', toolEvents: [], artifacts: [], actionPlans: [] });
        }
        const message = messages.value[aiMessageIndex];
        if (event.type === 'artifact') {
          message.artifacts = [...(message.artifacts || []), event.artifact];
          window.dispatchEvent(new CustomEvent('trailsnap:artifact-updated', { detail: event.artifact }));
        } else if (event.type === 'action_plan') {
          message.actionPlans = [...(message.actionPlans || []), event.action_plan];
        } else if (event.type === 'tool_start') {
          message.toolEvents = [...(message.toolEvents || []), event];
        } else {
          const current = [...(message.toolEvents || [])];
          const index = current.findIndex(item => item.tool_call_id === event.tool_call_id);
          if (index >= 0) current[index] = event;
          else current.push(event);
          message.toolEvents = current;
        }
        scrollToBottom();
      }
    );

    if (currentSession.value) {
      await loadMessages(currentSession.value.id, false);
    } else {
      nextTick(() => {
        setupImageClick();
      });
    }

  } catch (error: any) {
    if (error.name === 'AbortError') {
      // 如果是用户主动终止，直接返回，不报错，保留当前已经输出的内容在页面上
      return;
    }
    let errorMsg = '对话失败，请重试';
    if (error.response?.data?.detail) {
      errorMsg = error.response.data.detail;
    } else if (error.message) {
      errorMsg = error.message;
    }
    ElMessage.error(errorMsg);
    messages.value.push({ 
      role: 'assistant', 
      content: `❌ ${errorMsg}` 
    });
  } finally {
    isLoading.value = false;
    isGenerating.value = false;
    abortController.value = null;
    runningSessionId.value = null;
    nextTick(() => {
      scrollToBottom();
    });
  }
};

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    loadModels();
    loadSessions();
    loadProactiveMessages();
    scrollToBottom(true);
  }
});

onMounted(() => {
  if (props.modelValue) {
    loadModels();
    loadSessions();
    loadProactiveMessages();
    scrollToBottom();
  }
});
</script>

<style scoped>
.agent-chat-overlay {
  @apply fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/20 backdrop-blur-sm sm:p-4 transition-all duration-300;
}

.agent-chat-overlay.is-fullscreen {
  @apply sm:p-0;
}

.agent-chat-container {
  @apply w-full sm:w-[450px] h-[85vh] sm:h-[600px] max-h-screen bg-white dark:bg-slate-900 sm:rounded-2xl shadow-2xl flex overflow-hidden sm:border border-slate-200 dark:border-slate-800 transition-all duration-300;
  animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.agent-chat-container.has-sidebar {
  @apply sm:w-[706px];
}

.agent-chat-container.is-fullscreen {
  @apply w-full h-full sm:w-full sm:h-full sm:rounded-none sm:border-none sm:p-0;
}

/* 移动端侧边栏遮罩：z-index 15 位于 header(10) 与 sidebar(20) 之间，遮住主区域并点击关闭侧边栏 */
.agent-sidebar-backdrop {
  @apply absolute inset-0 bg-black/40 sm:hidden;
  z-index: 15;
  animation: backdropFadeIn 0.2s ease;
}

@keyframes backdropFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { transform: translateY(100%); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.agent-main {
  @apply flex-1 flex flex-col min-w-0 bg-white dark:bg-slate-900 h-full;
}

.agent-chat-messages {
  @apply flex-1 overflow-y-auto p-4 scroll-smooth;
}

.message-wrapper {
  @apply flex items-end gap-2 w-full;
}

.message-avatar {
  @apply w-7 h-7 rounded-full flex items-center justify-center shrink-0 mb-1;
}

.message-avatar.assistant {
  @apply bg-indigo-100 text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-400;
}

.message-bubble {
  @apply rounded-2xl px-4 py-2.5 text-sm shadow-sm transition-opacity duration-200;
}

.message-bubble.assistant {
  @apply bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-100 dark:border-slate-700 rounded-bl-sm;
}

/* Markdown Styles */
:deep(.markdown-body) {
  @apply text-sm leading-relaxed;
}

:deep(.markdown-body p) {
  @apply mb-2 last:mb-0;
}

:deep(.markdown-body strong) {
  @apply font-semibold text-slate-900 dark:text-white;
}

:deep(.markdown-body ul) {
  @apply list-disc pl-5 mb-2;
}

/* Custom Gallery Layout for AI returned images (CSS Grid 布局) */
:deep(.agent-gallery-grid) {
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  gap: 4px !important;
  margin: 12px 0 !important;
  padding: 0 !important;
  background-color: transparent !important;
  width: 100%;
  box-sizing: border-box;
}

:deep(.agent-gallery-item) {
  position: relative;
  width: 100%;
  padding-bottom: 100%; 
  overflow: hidden;
  border-radius: 6px;
  background-color: rgb(241 245 249);
}

:deep(.dark .agent-gallery-item) {
  background-color: rgb(30 41 59);
}

:deep(.agent-gallery-image) {
  position: absolute;
  top: 0;
  left: 0;
  width: 100% !important;
  height: 100% !important;
  object-fit: cover !important;
  margin: 0 !important;
  padding: 0 !important;
  display: block !important;
  cursor: pointer;
  border: none !important;
  transition: filter 0.2s ease;
}

:deep(.agent-gallery-image.inline-image) {
  position: relative;
  width: auto !important;
  max-width: 100% !important;
  height: auto !important;
  border-radius: 8px;
}

:deep(.agent-gallery-item:hover .agent-gallery-image) {
  filter: brightness(0.85);
}
</style>
