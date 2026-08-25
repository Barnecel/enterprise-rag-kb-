<template>
  <div class="chat-container">
    <!-- 窄屏抽屉遮罩 -->
    <div v-if="convMobileOpen" class="conv-backdrop" @click="convMobileOpen = false"></div>

    <!-- 对话边栏（DeepSeek 式全高） -->
    <aside class="conv-sidebar" :class="{ collapsed: convCollapsed, 'drawer-open': convMobileOpen }">
      <div class="conv-sidebar-head">
        <div class="conv-brand">
          <span class="conv-logo">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L19.7 10l-5.8 1.9L12 17.7l-1.9-5.8L4.3 10l5.8-1.2z"/></svg>
          </span>
          <span class="conv-brand-name">企业知识库</span>
        </div>
        <button class="conv-new-btn" @click="handleNewConversation">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
          <span>新对话</span>
        </button>
      </div>

      <div v-if="conversations.length" class="conv-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === activeConvId }"
          @click="switchConversation(conv)"
        >
          <template v-if="renamingId === conv.id">
            <el-input
              v-model="renameText"
              size="small"
              class="conv-rename-input"
              autofocus
              @click.stop
              @keyup.enter="confirmRename(conv)"
              @keyup.esc="renamingId = null"
              @blur="confirmRename(conv)"
            />
          </template>
          <template v-else>
            <div class="conv-item-title" :title="conv.title" @dblclick="startRename(conv)">{{ conv.title }}</div>
            <div class="conv-item-sub">{{ conv.last_question || '新对话' }}</div>
            <div class="conv-item-actions">
              <button class="conv-act" title="重命名" @click.stop="startRename(conv)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="conv-act danger" title="删除" @click.stop="handleDeleteConversation(conv)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
              </button>
            </div>
          </template>
        </div>
      </div>
      <div v-else class="conv-empty">
        <p>暂无对话</p>
        <p>点击上方"新对话"开始</p>
      </div>
    </aside>

    <!-- 主聊天区 -->
    <div class="chat-main">
      <!-- 悬浮：切换对话边栏（桌面收起 / 窄屏抽屉） -->
      <button class="conv-toggle" :class="{ on: !convCollapsed }" @click="toggleConvSidebar" title="对话列表">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
      </button>

      <div class="chat-messages" ref="messagesRef">
        <!-- 空态：DeepSeek 式居中大输入框 -->
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-logo">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L19.7 10l-5.8 1.9L12 17.7l-1.9-5.8L4.3 10l5.8-1.2z"/><path d="M19 15l.7 2.2L22 18l-2.3.8L19 21l-.7-2.2L16 18l2.3-.8z"/></svg>
          </div>
          <h1 class="empty-title">我能为你做点什么？</h1>
          <p class="empty-sub">基于企业知识库的 RAG 智能问答系统，快速查找文档答案</p>

          <div class="ds-input ds-input--center">
            <el-input
              ref="emptyInputRef"
              v-model="inputText"
              type="textarea"
              :rows="3"
              placeholder="输入你的问题，Enter 发送，Shift+Enter 换行..."
              resize="none"
              @keydown.enter="handleEnter"
            />
            <button class="ds-send" :class="{ disabled: sending }" :disabled="sending" @click="handleSend" title="发送">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
            </button>
          </div>

          <div class="suggestions">
            <span class="suggestion-item" v-for="(item, index) in suggestions" :key="index" @click="handleSuggestion(item)">
              {{ item }}
            </span>
          </div>
        </div>

        <!-- 消息列表 -->
        <div v-else class="message-list">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            :class="['message-item', msg.type]"
          >
            <div class="message-avatar">
              <svg v-if="msg.type === 'user'" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.2-4 4.5-6 8-6s6.8 2 8 6"/></svg>
              <svg v-else width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L19.7 10l-5.8 1.9L12 17.7l-1.9-5.8L4.3 10l5.8-1.2z"/></svg>
            </div>
            <div class="message-content">
              <!-- 思考动态状态 -->
              <div v-if="msg.thinking" class="thinking-bubble">
                <span class="thinking-dots"><i></i><i></i><i></i></span>
                <span class="thinking-text">{{ msg.statusText }}</span>
              </div>
              <div v-else class="message-text" v-html="formatMessage(msg.content)"></div>
              <div class="message-time">{{ msg.time }}</div>
              <!-- 显示参考文档 -->
              <div v-if="msg.type === 'ai' && msg.documents && msg.documents.length > 0" class="source-docs">
                <div class="docs-title">参考文档：</div>
                <div class="doc-item" v-for="doc in msg.documents" :key="doc.id">
                  <a class="doc-name" :title="'打开文档：' + (doc.title || '')" @click.prevent="openDocument(doc)">{{ doc.title || '文档' + doc.id }}{{ doc.page ? ' · 第' + doc.page + '页' : '' }}</a>
                  <span v-if="doc.rerank_norm != null || doc.score != null" class="doc-score">相似度: {{ ((doc.rerank_norm || doc.score || 0) * 100).toFixed(1) }}%</span>
                </div>
              </div>
              <!-- 反馈按钮（仅 AI 消息） -->
              <div v-if="msg.type === 'ai'" class="feedback-btns">
                <el-button
                  size="small"
                  type="primary"
                  :plain="msg.feedback_given !== 1"
                  circle
                  @click="submitFeedback(msg, 1)"
                  :disabled="sending"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  :plain="msg.feedback_given !== -1"
                  circle
                  @click="submitFeedback(msg, -1)"
                  :disabled="sending"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3l7 5 7-5v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"/></svg>
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部输入栏（有消息时） -->
      <div v-if="messages.length > 0" class="chat-input">
        <div class="ds-input ds-input--bottom">
          <el-input
            ref="bottomInputRef"
            v-model="inputText"
            type="textarea"
            :rows="2"
            placeholder="输入你的问题，Enter 发送，Shift+Enter 换行..."
            resize="none"
            @keydown.enter="handleEnter"
          />
          <button class="ds-send" :class="{ disabled: sending }" :disabled="sending" @click="handleSend" title="发送">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'Chat' })
import { ref, reactive, nextTick, onMounted, onActivated, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { qaAPI } from '../api'

const router = useRouter()

// 点击参考文档：打开对应该文档的全屏详情页（预览 + 元数据）
const openDocument = (doc) => {
  const id = Number(doc.id)
  if (!id) {
    ElMessage.warning('该文档不存在')
    return
  }
  router.push(`/document/${id}`)
}

const messagesRef = ref(null)
const emptyInputRef = ref(null)
const bottomInputRef = ref(null)
const inputText = ref('')
const sending = ref(false)
const messages = ref([])

// 会话边栏状态
const conversations = ref([])
const activeConvId = ref(null)
const convCollapsed = ref(false)   // 桌面端：收起/展开
const convMobileOpen = ref(false)  // 窄屏：抽屉开关
const renamingId = ref(null)
const renameText = ref('')
const isMobileWidth = () => window.innerWidth < 760

// 用户是否主动上滑（上滑后停止自动跟随滚动，避免抖动）
let userScrolledUp = false
const SCROLL_THRESHOLD = 100

// 建议问题
const suggestions = [
  '员工考勤时间是什么？',
  '如何申请年假？',
  '报销流程是什么？',
  '公司有哪些核心产品功能？'
]

// 处理建议问题点击
const handleSuggestion = (question) => {
  inputText.value = question
  handleSend()
}

// 格式化消息内容
const formatMessage = (content) => {
  return (content || '').replace(/\n/g, '<br>')
}

// 聚焦当前可见输入框
const focusInput = () => {
  nextTick(() => {
    const ref = messages.value.length === 0 ? emptyInputRef : bottomInputRef
    if (ref.value) ref.value.focus()
  })
}

// 切换/收起对话边栏
const toggleConvSidebar = () => {
  if (isMobileWidth()) {
    convMobileOpen.value = !convMobileOpen.value
  } else {
    convCollapsed.value = !convCollapsed.value
  }
}

// 刷新会话列表（不自动切换，保持当前会话）
const refreshConversationList = async () => {
  try {
    const res = await qaAPI.getConversations()
    conversations.value = res.data || []
  } catch (error) {
    console.error('刷新会话列表失败:', error)
  }
}

// 切换会话：加载该会话全部消息
const switchConversation = async (conv, silent = false) => {
  if (sending.value) {
    if (!silent) ElMessage.warning('回答生成中，请稍候')
    return
  }
  if (renamingId.value) renamingId.value = null
  activeConvId.value = conv.id
  localStorage.setItem('kb_active_conv', conv.id)
  if (convMobileOpen.value) convMobileOpen.value = false
  messages.value = []
  try {
    const res = await qaAPI.getConversationMessages(conv.id)
    messages.value = (res.data || []).flatMap(row => [
      {
        type: 'user',
        content: row.question,
        time: row.created_at
      },
      {
        type: 'ai',
        content: row.answer,
        time: row.created_at,
        history_id: row.id,
        documents: (row.documents || []).map(d => ({ id: d.id, title: d.title, rerank_norm: null, score: null }))
      }
    ])
  } catch (error) {
    console.error('加载会话消息失败:', error)
  }
  nextTick(() => scrollToBottom(true))
}

// 新建对话
const handleNewConversation = async () => {
  if (sending.value) return
  try {
    const res = await qaAPI.createConversation()
    const conv = { id: res.data.id, title: res.data.title, message_count: 0, last_question: '' }
    conversations.value.unshift(conv)
    activeConvId.value = conv.id
    localStorage.setItem('kb_active_conv', conv.id)
    messages.value = []
    inputText.value = ''
    if (convMobileOpen.value) convMobileOpen.value = false
    focusInput()
  } catch (error) {
    console.error('新建对话失败:', error)
  }
}

// 删除对话
const handleDeleteConversation = async (conv) => {
  try {
    await ElMessageBox.confirm('确定删除该对话及其全部消息吗？', '删除对话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  if (sending.value && conv.id === activeConvId.value) {
    ElMessage.warning('回答生成中，请稍候再删除')
    return
  }
  try {
    await qaAPI.deleteConversation(conv.id)
    conversations.value = conversations.value.filter(c => c.id !== conv.id)
    if (conv.id === activeConvId.value) {
      activeConvId.value = null
      if (conversations.value.length) {
        await switchConversation(conversations.value[0])
      } else {
        await handleNewConversation()
      }
    }
  } catch (error) {
    console.error('删除对话失败:', error)
  }
}

// 双击重命名
const startRename = (conv) => {
  if (sending.value) return
  renamingId.value = conv.id
  renameText.value = conv.title
}
const confirmRename = async (conv) => {
  if (renamingId.value !== conv.id) return
  const title = renameText.value.trim()
  renamingId.value = null
  if (!title || title === conv.title) return
  try {
    await qaAPI.renameConversation(conv.id, title)
    conv.title = title
  } catch (error) {
    console.error('重命名失败:', error)
  }
}

// 初始化会话列表：无会话则新建，否则恢复上次选中的会话
const initConversations = async () => {
  try {
    const res = await qaAPI.getConversations()
    conversations.value = res.data || []
    if (!conversations.value.length) {
      await handleNewConversation()
      return
    }
    const savedId = Number(localStorage.getItem('kb_active_conv')) || null
    const target = conversations.value.find(c => c.id === savedId) || conversations.value[0]
    await switchConversation(target, true)
  } catch (error) {
    console.error('初始化会话失败:', error)
  }
}

// 处理Enter键发送
const handleEnter = (e) => {
  if (!e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// 发送消息（流式输出）
const handleSend = async () => {
  const question = inputText.value.trim()
  if (!question) {
    ElMessage.warning('请输入问题')
    return
  }

  if (sending.value) return

  // 确保有活动会话（无则自动新建）
  let convId = activeConvId.value
  if (!convId) {
    try {
      const res = await qaAPI.createConversation()
      conversations.value.unshift({ id: res.data.id, title: res.data.title, message_count: 0, last_question: '' })
      activeConvId.value = convId = res.data.id
      localStorage.setItem('kb_active_conv', convId)
    } catch (error) {
      console.error('创建会话失败:', error)
      return
    }
  }

  // 添加用户消息
  messages.value.push({
    type: 'user',
    content: question,
    time: new Date().toLocaleString()
  })

  inputText.value = ''
  sending.value = true
  userScrolledUp = false
  scrollToBottom(true)

  // 添加AI占位消息（思考动态状态）
  const aiMsg = reactive({
    type: 'ai',
    thinking: true,
    statusText: '正在检索知识库...',
    content: '',
    documents: [],
    time: ''
  })
  messages.value.push(aiMsg)
  scrollToBottom(true)

  try {
    await qaAPI.askStream({ question, conversation_id: convId }, {
      onStatus: (event) => {
        // 服务端可能新建了会话（首问自动创建），同步当前会话ID
        if (event.phase === 'conversation' && event.conversation_id) {
          activeConvId.value = event.conversation_id
          localStorage.setItem('kb_active_conv', event.conversation_id)
          refreshConversationList()
        }
        aiMsg.statusText = event.phase === 'thinking' ? '正在思考...' : '正在检索知识库...'
        if (event.phase === 'thinking') {
          aiMsg.documents = event.retrieved_docs || []
        }
        // 回答落库后服务端补发 history_id，供反馈按钮使用
        if (event.phase === 'saved' && event.history_id) {
          aiMsg.history_id = event.history_id
        }
        scrollToBottom()
      },
      onToken: (delta) => {
        // 首个token到达：思考态转为流式正文
        if (aiMsg.thinking) {
          aiMsg.thinking = false
          aiMsg.content = ''
          aiMsg.time = new Date().toLocaleString()
        }
        aiMsg.content += delta
        scrollToBottom()
      },
      onDone: (event) => {
        aiMsg.thinking = false
        aiMsg.time = new Date().toLocaleString()
        scrollToBottom()
      },
      onError: (err) => {
        console.error('流式应答错误:', err)
        aiMsg.thinking = false
        aiMsg.content = '抱歉，发生了错误，请稍后重试。'
        aiMsg.time = new Date().toLocaleString()
        scrollToBottom()
      }
    })
  } catch (error) {
    console.error('发送失败:', error)
    aiMsg.thinking = false
    aiMsg.content = '抱歉，发生了错误，请稍后重试。'
    aiMsg.time = new Date().toLocaleString()
    scrollToBottom()
  } finally {
    sending.value = false
    // 流结束后刷新会话列表（标题/消息数/排序更新）
    refreshConversationList()
  }
}

// 判断用户是否停留在底部附近
const isNearBottom = () => {
  const el = messagesRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD
}

// 滚动到底部；force=true 强制滚动（发送新消息时），否则仅在用户未上滑时跟随
const scrollToBottom = (force = false) => {
  nextTick(() => {
    const el = messagesRef.value
    if (!el) return
    if (force || !userScrolledUp) {
      el.scrollTop = el.scrollHeight
    }
  })
}

// 提交反馈（点赞/点踩）；点踩可选填原因，重复提交即修改（后端幂等 upsert）
const submitFeedback = async (msg, rating) => {
  const historyId = msg.history_id
  if (!historyId) {
    ElMessage.warning('该回答尚未保存完成，请稍后再评价')
    return
  }
  let reason = ''
  if (rating === -1) {
    try {
      const { value } = await ElMessageBox.prompt(
        '这条回答哪里不满意？帮助我们一起改进（可选）', '反馈问题',
        { confirmButtonText: '提交', cancelButtonText: '跳过', inputPlaceholder: '例如：答案不准确 / 没有引用文档...', inputValidator: (v) => !v || v.length <= 255 || '最多255字' }
      )
      reason = (value || '').trim()
    } catch {
      // 用户取消也照常提交差评，只是不带原因
    }
  }
  try {
    await qaAPI.submitFeedback({ history_id: historyId, rating, reason })
    msg.feedback_given = rating
    ElMessage.success(rating === 1 ? '感谢认可！' : '已收到反馈，我们会改进')
  } catch (error) {
    console.error('提交反馈失败:', error)
  }
}

// 监听用户滚动意图：上滑查看历史时停止自动跟随
const onScroll = () => {
  userScrolledUp = !isNearBottom()
}

onMounted(() => {
  messagesRef.value.addEventListener('scroll', onScroll, { passive: true })
  initConversations()
  scrollToBottom()
})

// keep-alive 重新激活（从其他页面切回聊天）时，跟随到底部并刷新会话列表
onActivated(() => {
  scrollToBottom()
  if (activeConvId.value) refreshConversationList()
})

onBeforeUnmount(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', onScroll)
  }
})
</script>

<style scoped>
.chat-container {
  height: 100%;
  display: flex;
  background: var(--bg);
  overflow: hidden;
}

/* ===== 对话边栏 ===== */
.conv-sidebar {
  width: 260px;
  flex: none;
  border-right: 1px solid var(--border);
  background: var(--sidebar);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width .2s ease;
}
.conv-sidebar.collapsed {
  width: 0;
  border-right: none;
}

.conv-sidebar-head {
  padding: var(--space-5) var(--space-4) var(--space-3);
  border-bottom: 1px solid var(--border);
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.conv-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.conv-logo {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--grad-mark);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.conv-brand-name {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--text);
}
.conv-new-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 38px;
  border-radius: 980px;
  border: none;
  background: var(--grad-btn);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: filter .18s, transform .18s;
}
.conv-new-btn:hover { filter: brightness(1.06); }
.conv-new-btn:active { transform: scale(.98); }

.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.conv-item {
  position: relative;
  padding: var(--space-3);
  border-radius: 10px;
  cursor: pointer;
  transition: background .15s;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.conv-item:hover { background: var(--hover); }
.conv-item.active { background: var(--hover2); }
.conv-item-title {
  font-size: 13.5px;
  color: var(--text);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-item-sub {
  font-size: 11.5px;
  color: var(--text3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-item-actions {
  position: absolute;
  right: var(--space-2);
  top: var(--space-2);
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity .15s;
}
.conv-item:hover .conv-item-actions,
.conv-item.active .conv-item-actions { opacity: 1; }
.conv-act {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  border: none;
  background: var(--bg);
  color: var(--text3);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all .15s;
}
.conv-act:hover { background: var(--hover); color: var(--text); }
.conv-act.danger:hover { color: #ff3b30; background: rgba(255, 59, 48, .12); }
.conv-rename-input { width: 100%; }
.conv-rename-input :deep(.el-input__wrapper) {
  border-radius: 8px;
  background: var(--bg);
  box-shadow: 0 0 0 1px var(--primary) inset;
}

.conv-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: var(--text3);
  font-size: 12.5px;
  padding: var(--space-4);
  text-align: center;
}
.conv-empty p { margin: 0; }

/* 窄屏遮罩 */
.conv-backdrop {
  position: fixed;
  inset: 56px 0 0 0;
  z-index: 30;
  background: rgba(0, 0, 0, .4);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  display: none;
  animation: backdrop-in .2s ease;
}
@keyframes backdrop-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* ===== 主聊天区 ===== */
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* 悬浮：边栏切换按钮 */
.conv-toggle {
  position: absolute;
  top: var(--space-4);
  left: var(--space-4);
  z-index: 10;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text2);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all .18s;
  box-shadow: var(--shadow);
}
.conv-toggle:hover { background: var(--hover); color: var(--text); }
.conv-toggle.on { color: var(--primary); }

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-7);
}

/* ===== 空态：DeepSeek 居中大输入框 ===== */
.empty-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  max-width: 760px;
  margin: 0 auto;
  gap: 0;
}
.empty-logo {
  width: 72px;
  height: 72px;
  border-radius: 20px;
  background: var(--grad-mark);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-6);
  box-shadow: 0 8px 24px rgba(0, 113, 227, .25);
}
.empty-title {
  margin: 0 0 var(--space-3) 0;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -.02em;
  color: var(--text);
}
.empty-sub {
  margin: 0 0 var(--space-7) 0;
  color: var(--text3);
  font-size: 14px;
  text-align: center;
}

/* ===== DeepSeek 式输入框 ===== */
.ds-input { position: relative; width: 100%; }
.ds-input--center { max-width: 720px; }
.ds-input--bottom { max-width: 768px; margin: 0 auto; }
.ds-input :deep(.el-textarea__inner) {
  border-radius: 18px;
  background: var(--card);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  color: var(--text);
  line-height: 1.6;
  transition: border-color .2s, box-shadow .2s;
}
.ds-input--center :deep(.el-textarea__inner) {
  padding: var(--space-5);
  padding-right: 64px;
  font-size: 15px;
}
.ds-input--bottom :deep(.el-textarea__inner) {
  padding: var(--space-3) var(--space-4);
  padding-right: 60px;
  font-size: 14.5px;
}
.ds-input :deep(.el-textarea__inner:focus) {
  border-color: var(--primary);
  box-shadow: 0 0 0 4px var(--primary-soft), var(--shadow);
}
.ds-send {
  position: absolute;
  right: 10px;
  bottom: 10px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: var(--grad-btn);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: filter .18s, transform .18s;
}
.ds-send:hover { filter: brightness(1.06); }
.ds-send:active { transform: scale(.95); }
.ds-send.disabled { opacity: .55; cursor: not-allowed; }

/* 建议问题 */
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  justify-content: center;
  margin-top: var(--space-6);
}
.suggestion-item {
  padding: var(--space-2) var(--space-4);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 980px;
  font-size: 13px;
  color: var(--text2);
  cursor: pointer;
  transition: all .18s;
}
.suggestion-item:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-soft);
}

/* ===== 消息列表 ===== */
.message-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: 780px;
  margin: 0 auto;
  padding-top: var(--space-8);
}

.message-item {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}
.message-item.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.message-item.user .message-avatar {
  background: var(--grad-ava);
  color: #fff;
}

.message-content {
  max-width: 82%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.message-item.user .message-content {
  align-items: flex-end;
}

.message-text {
  padding: var(--space-3) var(--space-4);
  border-radius: 18px;
  line-height: 1.65;
  font-size: 14.5px;
  word-break: break-word;
}
.message-item.user .message-text {
  background: var(--grad-input);
  color: #fff;
  border-top-right-radius: 6px;
}
.message-item.ai .message-text {
  background: var(--card);
  border: 1px solid var(--border);
  border-top-left-radius: 6px;
  box-shadow: var(--shadow);
  color: var(--text);
}

.message-time {
  font-size: 12px;
  color: var(--text3);
  margin-top: var(--space-2);
}

/* 思考动态状态 */
.thinking-bubble {
  padding: var(--space-4) var(--space-5);
  border-radius: 18px;
  background: var(--card);
  border: 1px solid var(--border);
  border-top-left-radius: 6px;
  box-shadow: var(--shadow);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 44px;
}
.thinking-dots {
  display: inline-flex;
  gap: var(--space-1);
}
.thinking-dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  animation: thinking-bounce 1.2s infinite ease-in-out;
}
.thinking-dots i:nth-child(2) { animation-delay: 0.15s; }
.thinking-dots i:nth-child(3) { animation-delay: 0.3s; }

@keyframes thinking-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
.thinking-text {
  font-size: 13px;
  color: var(--text3);
}

/* 参考文档 */
.source-docs {
  margin-top: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  font-size: 12px;
  width: 100%;
}
.docs-title {
  color: var(--text2);
  margin-bottom: var(--space-2);
  font-weight: 500;
}
.doc-item {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-1) 0;
  border-bottom: 1px dashed var(--border);
}
.doc-item:last-child { border-bottom: none; }
.doc-name {
  color: var(--primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  text-decoration: none;
  border-radius: 6px;
  transition: background .15s;
}
.doc-name:hover {
  text-decoration: underline;
  background: var(--primary-soft);
}
.doc-item:has(.doc-name:hover) .doc-score { color: var(--primary); }
.doc-score {
  color: var(--text3);
  flex: none;
}

/* 底部输入栏 */
.chat-input {
  padding: var(--space-4) var(--space-6) var(--space-6);
  background: var(--bg);
  flex: none;
}

/* 反馈按钮 */
.feedback-btns {
  display: flex;
  gap: 8px;
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px dashed var(--border);
}
.feedback-btns :deep(.el-button--circle) {
  width: 28px;
  height: 28px;
  padding: 0;
}
.feedback-btns :deep(.el-button--primary:not(.is-plain)) {
  background: var(--grad-btn);
  border-color: transparent;
}
.feedback-btns :deep(.el-button--danger:not(.is-plain)) {
  background: linear-gradient(135deg, #ff4d4f, #ff7875);
  border-color: transparent;
}
.feedback-btns :deep(.el-button--primary.is-plain),
.feedback-btns :deep(.el-button--danger.is-plain) {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text2);
}
.feedback-btns :deep(.el-button--primary.is-plain:hover),
.feedback-btns :deep(.el-button--danger.is-plain:hover) {
  background: var(--hover);
}
.feedback-btns :deep(.el-button--primary.is-plain:not(:disabled):hover) {
  color: var(--primary);
  border-color: var(--primary);
}
.feedback-btns :deep(.el-button--danger.is-plain:not(:disabled):hover) {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

/* ===== 窄屏：对话边栏转抽屉 ===== */
@media (max-width: 760px) {
  .conv-backdrop { display: block; }
  .conv-sidebar {
    position: fixed;
    top: 56px;
    bottom: 0;
    left: 0;
    width: 260px;
    transform: translateX(-100%);
    transition: transform .25s ease;
    box-shadow: var(--shadow-hover);
    z-index: 40;
  }
  .conv-sidebar.drawer-open { transform: none; }
  .conv-sidebar.collapsed {
    width: 260px;
    border-right: 1px solid var(--border);
  }
  .chat-messages { padding: var(--space-6) var(--space-4); }
  .empty-title { font-size: 24px; }
  .ds-input--center :deep(.el-textarea__inner) { padding: var(--space-4); padding-right: 60px; }
}
</style>
