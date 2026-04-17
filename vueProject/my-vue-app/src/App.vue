<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from '../axiosInstance.js'
import AdminPage from './components/AdminPage.vue'
import { smtGlossary } from './data/smtGlossary'

const CHAT_API = '/chat'
const SESSION_LIST_API = '/sessions'
const SESSION_CREATE_API = '/session'
const SESSION_DELETE_API = '/delete'
const CONVERSATION_API = '/conversations'
const MESSAGE_LIST_API = '/messages'
const SEND_MESSAGE_API = '/send'
const OPTIMIZE_CODE_API = '/optimizeCode'
const OPTIMIZE_RECORDS_BY_MESSAGE_API = '/optimizeRecords/byMessage'
const DELETE_OPTIMIZE_RECORD_API = '/deleteOptimizeRecord'
const AUTH_LOGIN_API = '/login'
const AUTH_REGISTER_API = '/register'
const UPDATE_PASSWORD_API = '/updatePassword'
const AUTH_STORAGE_KEY = 'veriask-auth'

const requestExamples = []

const activeReferenceTab = ref('glossary')
const inputText = ref('')
const isLoading = ref(false)
const isHistoryLoading = ref(false)
const historyError = ref('')
const transcriptRef = ref(null)
const sessions = ref([])
const activeSessionId = ref('')
const hasSessions = computed(() => sessions.value.length > 0)
const isAuthenticated = ref(false)
const authMode = ref('login')
const routePath = ref('/')
const authForm = ref({
  email: '',
  password: '',
  confirmPassword: '',
})
const authError = ref('')
const isAuthenticating = ref(false)
const profile = ref({
  displayName: '形式验证账号',
  account: 'verifier-01',
  email: 'verifier@example.com',
  avatar: '',
})
const userId = ref('')
const userType = ref(0)
const passwordForm = ref({
  newPassword: '',
  confirmPassword: '',
})
const passwordError = ref('')
const isPasswordUpdating = ref(false)
const isProfileDialogOpen = ref(false)
const isProfileMenuOpen = ref(false)
const optimizeDrawerVisible = ref(false)
const optimizeDrawerWidth = ref(0)
const optimizeRecordsLoading = ref(false)
const optimizeRecordsError = ref('')
const isOptimizingCode = ref(false)
const selectedOptimizeMessage = ref(null)
const selectedOptimizeRecords = ref([])
const selectedSystemMessageId = ref('')
const isResizingOptimizeDrawer = ref(false)
const isAdmin = computed(() => Number(userType.value) === 1)
const isAdminRoute = computed(() => routePath.value === '/admin')
const optimizeDrawerSize = computed(() => `${optimizeDrawerWidth.value || getDefaultOptimizeDrawerWidth()}px`)
const profileInitials = computed(() => {
  const source = profile.value.displayName || profile.value.account
  return source.slice(0, 2).toUpperCase()
})

const activeSession = computed(
  () => sessions.value.find((session) => session.id === activeSessionId.value) ?? sessions.value[0] ?? null,
)

const activeMessages = computed(() => activeSession.value?.messages ?? [])
const assistantMessages = computed(() => activeMessages.value.filter((message) => message.role === 'assistant'))
const activeSystemMessage = computed(() => {
  if (selectedSystemMessageId.value) {
    const selectedMessage =
      assistantMessages.value.find((message) => message.id === selectedSystemMessageId.value) ?? null
    if (selectedMessage) {
      return selectedMessage
    }
  }

  return assistantMessages.value[assistantMessages.value.length - 1] ?? null
})
const activeSmtCode = computed(() => {
  if (!activeSystemMessage.value) {
    return ''
  }
  return activeSystemMessage.value.smtCode || activeSystemMessage.value.content || ''
})
const latestOptimizeRecord = computed(() =>
  selectedOptimizeRecords.value.length
    ? selectedOptimizeRecords.value[selectedOptimizeRecords.value.length - 1]
    : null,
)
const selectedCompareRecord = computed(() => {
  if (!selectedOptimizeRecords.value.length) {
    return null
  }

  if (selectedOptimizeMessage.value?.optimizeRecordId) {
    const matchedRecord =
      selectedOptimizeRecords.value.find(
        (record) => String(record.id) === String(selectedOptimizeMessage.value.optimizeRecordId),
      ) ?? null
    if (matchedRecord) {
      return matchedRecord
    }
  }

  return latestOptimizeRecord.value
})
const compareOriginalCode = computed(() => {
  if (selectedCompareRecord.value?.originalCode) {
    return selectedCompareRecord.value.originalCode
  }
  return getOptimizationSourceCode(selectedOptimizeMessage.value)
})
const compareOptimizedCode = computed(() => selectedCompareRecord.value?.optimizedCode ?? '')
const assistantMessageSignature = computed(() => assistantMessages.value.map((message) => message.id).join('|'))

watch(
  () => activeMessages.value.length,
  async () => {
    if (!isAuthenticated.value) {
      return
    }
    await nextTick()
    scrollTranscript()
  },
)

watch(
  assistantMessageSignature,
  () => {
    const latestAssistantMessage = assistantMessages.value[assistantMessages.value.length - 1] ?? null
    selectedSystemMessageId.value = latestAssistantMessage?.id ?? ''
  },
  { immediate: true },
)

watch(
  activeSessionId,
  async (sessionId) => {
    selectedSystemMessageId.value = ''
    if (!sessionId || !isAuthenticated.value) {
      return
    }

    const session =
      sessions.value.find((item) => item.id === sessionId || item.conversationId === sessionId) ?? null

    if (session?.loaded) {
      await hydrateOptimizeResults(session.messages)
      return
    }

    await ensureSessionMessages(sessionId)
  },
)

watch(routePath, () => {
  ensureAccessibleRoute()
})

onMounted(async () => {
  optimizeDrawerWidth.value = getDefaultOptimizeDrawerWidth()
  syncRoutePath()
  if (typeof window !== 'undefined') {
    window.addEventListener('popstate', syncRoutePath)
    window.addEventListener('resize', handleWindowResize)
  }

  const restored = restoreAuthFromStorage()
  ensureAccessibleRoute()
  if (restored || isAuthenticated.value) {
    await fetchConversations()
    scrollTranscript(false)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('popstate', syncRoutePath)
    window.removeEventListener('resize', handleWindowResize)
  }
  stopOptimizeDrawerResize()
})

function createId() {
  return `id-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

function getOptimizeDrawerBounds() {
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1600
  const maxWidth = Math.max(420, viewportWidth - 32)
  const minWidth = Math.min(720, Math.max(360, maxWidth - 80))

  return {
    minWidth,
    maxWidth,
  }
}

function clampOptimizeDrawerWidth(width) {
  const { minWidth, maxWidth } = getOptimizeDrawerBounds()
  return Math.min(maxWidth, Math.max(minWidth, Math.round(width)))
}

function getDefaultOptimizeDrawerWidth() {
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1600
  return clampOptimizeDrawerWidth(viewportWidth * 0.58)
}

let optimizeDrawerResizeStartX = 0
let optimizeDrawerResizeStartWidth = 0

function beginOptimizeDrawerResize(event) {
  if (typeof window === 'undefined') {
    return
  }

  isResizingOptimizeDrawer.value = true
  optimizeDrawerResizeStartX = event.clientX
  optimizeDrawerResizeStartWidth = optimizeDrawerWidth.value || getDefaultOptimizeDrawerWidth()

  window.addEventListener('pointermove', handleOptimizeDrawerResize)
  window.addEventListener('pointerup', stopOptimizeDrawerResize)
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
}

function handleOptimizeDrawerResize(event) {
  if (!isResizingOptimizeDrawer.value) {
    return
  }

  const deltaX = optimizeDrawerResizeStartX - event.clientX
  optimizeDrawerWidth.value = clampOptimizeDrawerWidth(optimizeDrawerResizeStartWidth + deltaX)
}

function stopOptimizeDrawerResize() {
  if (typeof window !== 'undefined') {
    window.removeEventListener('pointermove', handleOptimizeDrawerResize)
    window.removeEventListener('pointerup', stopOptimizeDrawerResize)
  }

  if (typeof document !== 'undefined') {
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  }

  isResizingOptimizeDrawer.value = false
}

function handleWindowResize() {
  optimizeDrawerWidth.value = clampOptimizeDrawerWidth(optimizeDrawerWidth.value || getDefaultOptimizeDrawerWidth())
}

function createUserMessage(content) {
  return {
    id: createId(),
    optimizeTargetId: '',
    optimizeRecordId: '',
    role: 'user',
    replyKind: 'user',
    sourceMessageId: '',
    content,
    createdAt: new Date().toISOString(),
    sections: [],
    smtCode: '',
    optimizedCode: '',
    optimizedOriginalCode: '',
    optimizedAt: '',
    rawPayload: '',
  }
}

function createAssistantMessage(content, options = {}) {
  return {
    id: createId(),
    optimizeTargetId: options.optimizeTargetId ?? '',
    optimizeRecordId: options.optimizeRecordId ?? '',
    role: 'assistant',
    replyKind: options.replyKind ?? 'solve',
    sourceMessageId: options.sourceMessageId ?? '',
    content,
    createdAt: new Date().toISOString(),
    sections: options.sections ?? [],
    smtCode: options.smtCode ?? '',
    optimizedCode: options.optimizedCode ?? '',
    optimizedOriginalCode: options.optimizedOriginalCode ?? '',
    optimizedAt: options.optimizedAt ?? '',
    rawPayload: options.rawPayload ?? '',
  }
}

function normalizeRoutePath(path) {
  if (!path || path === '/') {
    return '/'
  }
  return path === '/admin' ? '/admin' : '/'
}

function syncRoutePath() {
  if (typeof window === 'undefined') {
    routePath.value = '/'
    return
  }
  routePath.value = normalizeRoutePath(window.location.pathname)
}

function navigateTo(path) {
  const targetPath = normalizeRoutePath(path)
  if (typeof window !== 'undefined' && window.location.pathname !== targetPath) {
    window.history.pushState({}, '', targetPath)
  }
  routePath.value = targetPath
}

function ensureAccessibleRoute() {
  if (routePath.value === '/admin' && (!isAuthenticated.value || !isAdmin.value)) {
    navigateTo('/')
  }
}

function createDraftSession() {
  return {
    id: createId(),
    conversationId: createId(),
    title: '未命名会话',
    updatedAt: new Date().toISOString(),
    messages: [],
    loaded: true,
    isDraft: true,
  }
}

function createEmptyAssistantMessage(errorText) {
  return createAssistantMessage(errorText, {
    sections: [
      {
        label: '排查建议',
        content: '请检查后端服务是否启动，并确认接口地址与 CORS 配置正确。',
      },
    ],
  })
}

async function fetchConversations(preferredConversationId = '') {
  if (!isAuthenticated.value || !userId.value) {
    return
  }
  isHistoryLoading.value = true
  historyError.value = ''

  try {
    const response = await axios.get(SESSION_LIST_API, {
      params: {
        userId: userId.value,
      },
    })

    const raw = response?.data ?? null
    const serverSessions = normalizeSessionList(raw)
    const draftSessions = sessions.value.filter((session) => session.isDraft)
    const mergedSessions = [
      ...draftSessions,
      ...serverSessions.filter(
        (serverSession) => !draftSessions.some((draftSession) => draftSession.conversationId === serverSession.conversationId),
      ),
    ]

    sessions.value = mergedSessions

    const nextActiveSession =
      findSessionByConversationId(preferredConversationId) ??
      sessions.value.find((session) => session.id === activeSessionId.value) ??
      sessions.value[0] ??
      null

    activeSessionId.value = nextActiveSession?.id ?? ''
  } catch (error) {
    historyError.value = `历史记录加载失败：${getErrorMessage(error)}`
  } finally {
    isHistoryLoading.value = false
  }
}

async function ensureSessionMessages(sessionIdOrConversationId, options = {}) {
  const session =
    sessions.value.find(
      (item) => item.id === sessionIdOrConversationId || item.conversationId === sessionIdOrConversationId,
    ) ?? null
  if (!session || session.isDraft || session.loaded === true) {
    return
  }

  try {
    const response = await axios.get(MESSAGE_LIST_API, {
      params: {
        sessionId: session.conversationId,
      },
    })
    const raw = response?.data ?? null
    const detail = normalizeConversationDetail(raw)

    if (options.incremental) {
      mergeNewMessages(session, detail, { clearPending: true })
    } else {
      session.messages = detail.messages.length ? detail.messages : []
    }
    await hydrateOptimizeResults(session.messages)
    session.title = detail.title || session.title
    session.updatedAt = detail.updatedAt || session.updatedAt
    session.loaded = true
  } catch (error) {
    historyError.value = `读取会话详情失败：${getErrorMessage(error)}`
    session.messages = [createEmptyAssistantMessage('读取会话详情失败，请稍后重试。')]
    session.loaded = true
  }
}

async function startNewSession() {
  if (!isAuthenticated.value || !userId.value) {
    const draftSession = createDraftSession()
    sessions.value = [draftSession, ...sessions.value.filter((session) => session.id !== draftSession.id)]
    activeSessionId.value = draftSession.id
    inputText.value = ''
    return
  }

  const formData = new URLSearchParams()
  formData.append('userId', String(userId.value))
  formData.append('title', '未命名会话')

  try {
    const response = await axios.post(SESSION_CREATE_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const payload = extractPayload(response?.data ?? null)
    const createdSession = normalizeSession(payload)

    if (!createdSession) {
      throw new Error('创建会话返回为空')
    }

    createdSession.messages = createdSession.messages?.length ? createdSession.messages : []
    createdSession.loaded = createdSession.messages.length > 0
    createdSession.isDraft = false

    sessions.value = [createdSession, ...sessions.value.filter((session) => session.id !== createdSession.id)]
    activeSessionId.value = createdSession.id
    inputText.value = ''
  } catch (error) {
    historyError.value = `新建会话失败：${getErrorMessage(error)}`
  }
}

async function switchSession(sessionId) {
  activeSessionId.value = sessionId
}

async function removeSession(sessionId) {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    return
  }

  try {
    await ElMessageBox.confirm('确认删除这次会话吗？删除后将无法恢复。', '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  if (session.isDraft) {
    sessions.value = sessions.value.filter((item) => item.id !== sessionId)
    } else {
      try {
        const formData = new URLSearchParams()
        formData.append('sessionId', session.conversationId)

        const response = await axios.post(SESSION_DELETE_API, formData, {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
          },
        })
        const body = response?.data ?? null
        if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
          throw new Error(body.message || '删除会话失败')
        }
        sessions.value = sessions.value.filter((item) => item.id !== sessionId)
      } catch (error) {
        historyError.value = `删除会话失败：${getErrorMessage(error)}`
        return
      }
    }

  if (activeSessionId.value === sessionId) {
    activeSessionId.value = sessions.value[0]?.id ?? ''
  }

  if (!sessions.value.length) {
    inputText.value = ''
  }
}

function toggleProfileMenu() {
  isProfileMenuOpen.value = !isProfileMenuOpen.value
}

function startPasswordEdit() {
  passwordForm.value = {
    newPassword: '',
    confirmPassword: '',
  }
  passwordError.value = ''
  isProfileMenuOpen.value = false
  isProfileDialogOpen.value = true
}

function closeProfileDialog() {
  isProfileDialogOpen.value = false
  passwordError.value = ''
}

async function savePassword() {
  if (
    !passwordForm.value.newPassword.trim() ||
    !passwordForm.value.confirmPassword.trim()
  ) {
    passwordError.value = '请完整填写新密码信息'
    return
  }
  if (passwordForm.value.newPassword !== passwordForm.value.confirmPassword) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }

  if (!userId.value) {
    passwordError.value = '未获取到用户信息，请重新登录后重试'
    return
  }

  isPasswordUpdating.value = true
  passwordError.value = ''
  try {
    const formData = new URLSearchParams()
    formData.append('id', String(userId.value))
    formData.append('password', passwordForm.value.newPassword.trim())

    const response = await axios.post(UPDATE_PASSWORD_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const body = response?.data ?? null
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      throw new Error(body.message || '修改密码失败')
    }

    isProfileDialogOpen.value = false
    if (typeof window !== 'undefined') {
      window.alert('密码修改成功')
    }
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const serverMessage = error.response?.data?.message || error.response?.data
      passwordError.value =
        typeof serverMessage === 'string' && serverMessage.trim()
          ? serverMessage
          : error.message || '修改密码失败'
      return
    }
    passwordError.value = getErrorMessage(error)
  } finally {
    isPasswordUpdating.value = false
  }
}

function handleLogout() {
  isProfileMenuOpen.value = false
  isProfileDialogOpen.value = false
  if (typeof window !== 'undefined') {
    window.alert('已退出登录，即将返回登录页。')
  }
  userId.value = ''
  userType.value = 0
  isAuthenticated.value = false
  sessions.value = []
  activeSessionId.value = ''
  inputText.value = ''
  historyError.value = ''
  authMode.value = 'login'
  authForm.value = {
    email: '',
    password: '',
    confirmPassword: '',
  }
  authError.value = ''
  clearAuthStorage()
  navigateTo('/')
}

function openAdminView() {
  if (!isAdmin.value) {
    return
  }
  isProfileMenuOpen.value = false
  navigateTo('/admin')
}

function backToChatView() {
  navigateTo('/')
}

function switchAuthMode(mode) {
  if (authMode.value === mode) {
    return
  }
  authMode.value = mode
  authError.value = ''
  authForm.value = {
    email: '',
    password: '',
    confirmPassword: '',
  }
}

function validateAuthForm() {
  if (!authForm.value.email.trim() || !authForm.value.password.trim()) {
    return '请填写账号/邮箱和密码'
  }
  if (authMode.value === 'register') {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailPattern.test(authForm.value.email.trim())) {
      return '请输入正确的邮箱格式'
    }
    if (authForm.value.password !== authForm.value.confirmPassword) {
      return '两次输入的密码不一致'
    }
  }
  return ''
}

async function requestAuth(url, payload) {
  const formData = new URLSearchParams()
  formData.append('email', payload.email)
  formData.append('password', payload.password)

  let response
  try {
    response = await axios.post(url, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const serverMessage = error.response?.data?.message || error.response?.data
      if (typeof serverMessage === 'string' && serverMessage.trim()) {
        throw new Error(serverMessage)
      }
      throw new Error(error.message || '认证请求失败')
    }
    throw error
  }

  const body = response?.data ?? null
  if (body && typeof body === 'object' && 'code' in body) {
    if (body.code !== 200) {
      throw new Error(body.message || '认证失败')
    }
    return body.data ?? null
  }

  return body
}

async function submitAuth() {
  const validationError = validateAuthForm()
  if (validationError) {
    authError.value = validationError
    return
  }

  authError.value = ''
  isAuthenticating.value = true

  try {
    const email = authForm.value.email.trim()
    const password = authForm.value.password.trim()
    let authData = null

    if (authMode.value === 'login') {
      authData = await requestAuth(AUTH_LOGIN_API, {
        email,
        password,
      })
      applyAuthenticatedProfile(authData, email, '形式验证账号')
    } else {
      authData = await requestAuth(AUTH_REGISTER_API, {
        email,
        password,
      })
      applyAuthenticatedProfile(authData, email, '新用户')
    }

    isAuthenticated.value = true
    ensureAccessibleRoute()
    authForm.value = {
      email: '',
      password: '',
      confirmPassword: '',
    }
    await fetchConversations()
    scrollTranscript(false)
  } catch (error) {
    authError.value = getErrorMessage(error)
  } finally {
    isAuthenticating.value = false
  }
}
function fillExample(text) {
  inputText.value = text
}

function selectSystemMessage(message) {
  if (message?.role !== 'assistant') {
    return
  }
  selectedSystemMessageId.value = message.id
}

function isSelectedSystemMessage(message) {
  return message?.role === 'assistant' && message.id === activeSystemMessage.value?.id
}

function canOptimizeMessage(message) {
  return message?.role === 'assistant' && !!message.optimizeTargetId
}

function canCompareOptimize(message) {
  return message?.role === 'assistant' && message.replyKind === 'optimize' && !!message.optimizeTargetId
}

function canDeleteOptimize(message) {
  return message?.role === 'assistant' && message.replyKind === 'optimize' && !!message.optimizeRecordId
}

function getOptimizationSourceCode(message) {
  if (!message || message.role !== 'assistant') {
    return ''
  }
  return message.smtCode || message.content || ''
}

async function openOptimizeCompare(message) {
  if (!message?.optimizeTargetId) {
    return
  }

  selectSystemMessage(message)
  selectedOptimizeMessage.value = message
  optimizeDrawerVisible.value = true
  await fetchOptimizeRecordsByMessageId(message.optimizeTargetId)
}

async function fetchOptimizeRecordsByMessageId(messageId) {
  selectedOptimizeRecords.value = []
  optimizeRecordsError.value = ''
  optimizeRecordsLoading.value = true

  try {
    const response = await axios.get(OPTIMIZE_RECORDS_BY_MESSAGE_API, {
      params: {
        messageId,
      },
    })

    selectedOptimizeRecords.value = normalizeOptimizeRecords(response?.data ?? null)
    syncOptimizeReplyMessages(messageId, selectedOptimizeRecords.value)
    return selectedOptimizeRecords.value
  } catch (error) {
    optimizeRecordsError.value = `优化记录加载失败：${getErrorMessage(error)}`
    return []
  } finally {
    optimizeRecordsLoading.value = false
  }
}

async function optimizeMessage(message) {
  if (!message?.optimizeTargetId || isOptimizingCode.value) {
    return
  }

  selectSystemMessage(message)
  selectedOptimizeMessage.value = message
  isOptimizingCode.value = true
  optimizeRecordsError.value = ''

  try {
    const formData = new URLSearchParams()
    formData.append('messageId', message.optimizeTargetId)
    const originalCode = getOptimizationSourceCode(message)
    if (originalCode) {
      formData.append('originalCode', originalCode)
    }

    const response = await axios.post(OPTIMIZE_CODE_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const body = response?.data ?? null
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      throw new Error(body.message || '优化失败')
    }

    const records = await fetchOptimizeRecordsByMessageId(message.optimizeTargetId)
    const latestReplyMessage =
      activeMessages.value.findLast?.(
        (item) => item.replyKind === 'optimize' && item.sourceMessageId === message.id,
      ) ??
      [...activeMessages.value]
        .reverse()
        .find((item) => item.replyKind === 'optimize' && item.sourceMessageId === message.id) ??
      null
    if (latestReplyMessage) {
      selectSystemMessage(latestReplyMessage)
    }
    scrollTranscript()
    ElMessage.success(
      records.length > 1 ? '优化已完成，所有优化结果已更新到聊天区' : '优化已完成，结果已显示在聊天区',
    )
  } catch (error) {
    optimizeRecordsError.value = `优化失败：${getErrorMessage(error)}`
    ElMessage.error(getErrorMessage(error))
  } finally {
    isOptimizingCode.value = false
  }
}

async function deleteOptimizeMessage(message) {
  if (!canDeleteOptimize(message)) {
    return
  }

  try {
    await ElMessageBox.confirm('确认删除这条优化结果吗？', '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  try {
    const formData = new URLSearchParams()
    formData.append('optId', String(message.optimizeRecordId))

    const response = await axios.post(DELETE_OPTIMIZE_RECORD_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const body = response?.data ?? null
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      throw new Error(body.message || '删除优化结果失败')
    }

    await fetchOptimizeRecordsByMessageId(message.optimizeTargetId)
    ElMessage.success('优化结果已删除')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function submitQuestion() {
  const question = inputText.value.trim()
  if (!isAuthenticated.value || !question || isLoading.value || !activeSession.value) {
    return
  }

  const session = activeSession.value
  const userDraftMessage = createUserMessage(question)
  userDraftMessage.isPending = true
  session.messages.push(userDraftMessage)
  session.title = session.title === '未命名会话' ? buildSessionTitle(question) : session.title
  session.updatedAt = new Date().toISOString()

  inputText.value = ''
  isLoading.value = true

  try {
    const formData = new URLSearchParams()
    formData.append('sessionId', session.conversationId)
    formData.append('content', question)

    const response = await axios.post(SEND_MESSAGE_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const body = response?.data ?? null
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      throw new Error(body.message || '提交失败')
    }

    session.loaded = false
    await ensureSessionMessages(session.conversationId, { incremental: true })
    session.updatedAt = new Date().toISOString()
    session.isDraft = false
    sessions.value = [session, ...sessions.value.filter((item) => item.id !== session.id)]
    scrollTranscript()
  } catch (error) {
    session.messages.push(createEmptyAssistantMessage(getErrorMessage(error)))
    session.updatedAt = new Date().toISOString()
  } finally {
    isLoading.value = false
  }
}

function mergeNewMessages(session, detail, options = {}) {
  if (!detail.messages.length) {
    return
  }
  if (options.clearPending) {
    session.messages = session.messages.filter((message) => !message.isPending)
  }
  const existingIds = new Set(session.messages.map((message) => message.id))
  const incremental = detail.messages.filter((message) => !existingIds.has(message.id))
  if (incremental.length) {
    session.messages.push(...incremental)
  }
}

async function normalizeChatResponse(response) {
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText}`)
  }

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    const text = await response.text()
    return {
      answer: text || '后端返回了空响应内容。',
      smtCode: '',
      sections: [],
      rawPayload: text,
      conversationId: '',
    }
  }

  const raw = await response.json()
  const container = extractPayload(raw)

  return {
    answer:
      pickText(container, ['answer', 'result', 'content', 'message', 'reply', 'output']) ??
      pickText(raw, ['answer', 'result', 'content', 'message', 'reply', 'output']) ??
      '后端返回结果中未找到可展示的答案。',
    smtCode: pickText(container, ['smtCode', 'smt_code', 'code', 'script', 'solverInput', 'solver_input']) ?? '',
    sections: collectSections(container),
    rawPayload: JSON.stringify(raw, null, 2),
    conversationId: pickId(container, ['conversationId', 'sessionId', 'id']) ?? '',
  }
}

function normalizeSessionList(raw) {
  const container = extractPayload(raw)
  const list =
    pickArray(container, ['conversations', 'sessions', 'records', 'list']) ??
    pickArray(raw, ['conversations', 'sessions', 'records', 'list']) ??
    (Array.isArray(container) ? container : [])

  return list.map(normalizeSession).filter(Boolean)
}

function normalizeSession(source) {
  if (!source || typeof source !== 'object') {
    return null
  }

  const conversationId = pickId(source, ['conversationId', 'sessionId', 'id'])
  if (!conversationId) {
    return null
  }

  const messages = normalizeMessages(
    pickArray(source, ['messages', 'history', 'records']) ?? [],
  )

  return {
    id: conversationId,
    conversationId,
    title: pickText(source, ['title', 'subject', 'name']) ?? '未命名会话',
    updatedAt: pickText(source, ['updatedAt', 'updateTime', 'createdAt', 'createTime']) ?? new Date().toISOString(),
    messages,
    loaded: messages.length > 0,
    isDraft: false,
  }
}

function normalizeConversationDetail(raw) {
  const container = extractPayload(raw)
  const messages = normalizeMessages(
    pickArray(container, ['messages', 'history', 'records']) ??
      pickArray(raw, ['messages', 'history', 'records']) ??
      (Array.isArray(container) ? container : []),
  )

  return {
    title: pickText(container, ['title', 'subject', 'name']) ?? '',
    updatedAt: pickText(container, ['updatedAt', 'updateTime', 'createdAt', 'createTime']) ?? '',
    messages,
  }
}

function normalizeMessages(messages) {
  if (!Array.isArray(messages)) {
    return []
  }

  return messages
    .map((message) => {
      if (!message || typeof message !== 'object') {
        return null
      }

      const container = extractPayload(message)
      const content =
        pickText(container, ['content', 'answer', 'result', 'message', 'text']) ??
        pickText(message, ['content', 'answer', 'result', 'message', 'text']) ??
        ''

      if (!content) {
        return null
      }

      return {
        id: pickId(message, ['id', 'messageId']) ?? createId(),
        optimizeTargetId: pickId(message, ['id', 'messageId']) ?? '',
        optimizeRecordId: '',
        role: normalizeRole(pickText(message, ['role', 'senderType', 'type']) ?? 'assistant'),
        replyKind: 'solve',
        sourceMessageId: '',
        content,
        createdAt: pickText(message, ['createdAt', 'createTime', 'timestamp']) ?? new Date().toISOString(),
        sections: collectSections(container),
        smtCode: pickText(container, ['smtCode', 'smt_code', 'code', 'script', 'solverInput', 'solver_input']) ?? '',
        optimizedCode: '',
        optimizedOriginalCode: '',
        optimizedAt: '',
        rawPayload: '',
      }
    })
    .filter(Boolean)
}

function normalizeOptimizeRecord(raw) {
  return normalizeOptimizeRecords({ records: [extractPayload(raw)] })[0] ?? null
}

function normalizeOptimizeRecords(raw) {
  const container = extractPayload(raw)
  const list =
    pickArray(container, ['records', 'list']) ??
    pickArray(raw, ['records', 'list']) ??
    (Array.isArray(container) ? container : [])

  return list
    .map((record) => {
      if (!record || typeof record !== 'object') {
        return null
      }

      return {
        id: pickId(record, ['optId', 'opt_id', 'id']) ?? createId(),
        messageId: pickId(record, ['messageId', 'message_id']) ?? '',
        originalCode: pickText(record, ['originalCode', 'original_code']) ?? '',
        optimizedCode: pickText(record, ['optimizedCode', 'optimized_code', 'result']) ?? '',
        createTime: pickText(record, ['createTime', 'create_time', 'updatedAt']) ?? '',
      }
    })
    .filter(Boolean)
    .sort((left, right) => {
      const leftTime = left.createTime ? new Date(left.createTime).getTime() : 0
      const rightTime = right.createTime ? new Date(right.createTime).getTime() : 0
      if (leftTime !== rightTime) {
        return leftTime - rightTime
      }

      const leftId = Number(left.id) || 0
      const rightId = Number(right.id) || 0
      return leftId - rightId
    })
}

function applyOptimizeRecordToMessage(message, record) {
  if (!message || message.role !== 'assistant' || !record) {
    return
  }

  message.optimizedOriginalCode = record.originalCode || getOptimizationSourceCode(message)
  message.optimizedCode = record.optimizedCode || ''
  message.optimizedAt = record.createTime || ''
}

function buildOptimizeReplyMessage(sourceMessage, record) {
  if (!sourceMessage || !record) {
    return null
  }

  const replyId = `optimize-reply-${sourceMessage.optimizeTargetId || sourceMessage.id}-${record.id}`
  const replyMessage = createAssistantMessage(record.optimizedCode || '暂无优化结果', {
    optimizeTargetId: sourceMessage.optimizeTargetId,
    optimizeRecordId: record.id,
    replyKind: 'optimize',
    sourceMessageId: sourceMessage.id,
    createdAt: record.createTime || new Date().toISOString(),
    smtCode: record.optimizedCode || '',
  })
  replyMessage.id = replyId
  replyMessage.optimizedOriginalCode = record.originalCode || getOptimizationSourceCode(sourceMessage)
  replyMessage.optimizedCode = record.optimizedCode || ''
  replyMessage.optimizedAt = record.createTime || ''
  return replyMessage
}

function syncOptimizeReplyMessages(messageId, records, messages = activeMessages.value) {
  if (!Array.isArray(messages) || !messageId) {
    return []
  }

  const sourceMessage =
    messages.find(
      (message) => message.optimizeTargetId === String(messageId) && message.replyKind !== 'optimize',
    ) ?? null

  if (!sourceMessage) {
    return []
  }

  const sourceMessageId = sourceMessage.id
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.replyKind === 'optimize' && messages[index]?.sourceMessageId === sourceMessageId) {
      messages.splice(index, 1)
    }
  }

  if (!Array.isArray(records) || !records.length) {
    return []
  }

  const replyMessages = records
    .map((record) => buildOptimizeReplyMessage(sourceMessage, record))
    .filter(Boolean)

  const sourceIndex = messages.findIndex((message) => message.id === sourceMessageId)
  if (sourceIndex >= 0) {
    messages.splice(sourceIndex + 1, 0, ...replyMessages)
  } else {
    messages.push(...replyMessages)
  }

  return replyMessages
}

async function hydrateOptimizeResults(messages) {
  if (!Array.isArray(messages) || !messages.length) {
    return
  }

  const assistantMessages = messages.filter(
    (message) => message.role === 'assistant' && message.replyKind !== 'optimize' && message.optimizeTargetId,
  )

  await Promise.all(
    assistantMessages.map(async (message) => {
      try {
        const response = await axios.get(OPTIMIZE_RECORDS_BY_MESSAGE_API, {
          params: {
            messageId: message.optimizeTargetId,
          },
        })
        const records = normalizeOptimizeRecords(response?.data ?? null)
        syncOptimizeReplyMessages(message.optimizeTargetId, records, messages)
      } catch {
        // Ignore hydration failures and keep the chat usable.
      }
    }),
  )
}

function normalizeRole(role) {
  if (!role) {
    return 'assistant'
  }

  return ['user', 'human', 'question'].includes(role) ? 'user' : 'assistant'
}

function extractPayload(source) {
  if (!source || typeof source !== 'object') {
    return source
  }

  if (source.data && typeof source.data === 'object') {
    return source.data
  }

  if (source.payload && typeof source.payload === 'object') {
    return source.payload
  }

  if (source.result && typeof source.result === 'object') {
    return source.result
  }

  return source
}

function pickText(source, keys) {
  if (!source || typeof source !== 'object') {
    return typeof source === 'string' ? source : null
  }

  for (const key of keys) {
    const value = source[key]
    if (typeof value === 'string' && value.trim()) {
      return value
    }

    if (typeof value === 'number') {
      return String(value)
    }
  }

  return null
}

function pickArray(source, keys) {
  if (!source || typeof source !== 'object') {
    return null
  }

  for (const key of keys) {
    if (Array.isArray(source[key])) {
      return source[key]
    }
  }

  return null
}

function pickId(source, keys) {
  const value = pickText(source, keys)
  return value ? String(value) : null
}

function collectSections(source) {
  if (!source || typeof source !== 'object') {
    return []
  }

  const mapping = [
    ['status', '求解状态'],
    ['solveStatus', '求解状态'],
    ['explanation', '求解说明'],
    ['reason', '求解说明'],
    ['model', '模型输出'],
    ['modelValues', '模型输出'],
    ['unsatCore', 'Unsat Core'],
    ['unsat_core', 'Unsat Core'],
    ['proof', '证明信息'],
    ['constraints', '约束详情'],
    ['constraintList', '约束详情'],
    ['warnings', '警告'],
  ]

  return mapping
    .map(([key, label]) => {
      const value = source[key]
      if (value === undefined || value === null || value === '') {
        return null
      }

      return {
        label,
        content: typeof value === 'string' ? value : JSON.stringify(value, null, 2),
      }
    })
    .filter(Boolean)
}

function findSessionByConversationId(conversationId) {
  return sessions.value.find((session) => session.conversationId === conversationId) ?? null
}

function buildSessionTitle(text) {
  const cleanText = text.replace(/\s+/g, ' ').trim()
  return cleanText.slice(0, 22) || '未命名会话'
}

function scrollTranscript(smooth = true) {
  const element = transcriptRef.value
  if (!element) {
    return
  }

  element.scrollTo({
    top: element.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  })
}

function formatTime(value) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

async function copyText(content) {
  if (!content) {
    return
  }

  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(content)
      ElMessage.success('复制成功')
      return
    }
  } catch {
    // Fallback to legacy copy flow below.
  }

  if (typeof document === 'undefined') {
    ElMessage.error('当前环境不支持复制')
    return
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = content
    textarea.setAttribute('readonly', 'readonly')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    textarea.style.pointerEvents = 'none'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)

    const copied = document.execCommand('copy')
    document.body.removeChild(textarea)

    if (!copied) {
      throw new Error('copy failed')
    }

    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

function getErrorMessage(error) {
  if (error && typeof error === 'object') {
    const responseMessage = error.response?.data?.message || error.response?.data
    if (typeof responseMessage === 'string' && responseMessage.trim()) {
      return responseMessage
    }

    if (error.code === 'ECONNABORTED') {
      return '请求超时，后端处理时间较长，请稍后重试。'
    }
  }

  return error instanceof Error ? error.message : '请求失败，请稍后重试。'
}

function applyAuthenticatedProfile(authData, fallbackEmail, fallbackDisplayName) {
  const normalizedEmail = authData?.email || fallbackEmail || ''
  const normalizedAccount = authData?.account || normalizedEmail
  const normalizedId = authData?.id ?? authData?.userId ?? ''
  const normalizedUserType = Number(authData?.userType ?? authData?.user_type ?? 0)
  const normalizedDisplayName = authData?.displayName || fallbackDisplayName || normalizedAccount

  userId.value = normalizedId ? String(normalizedId) : ''
  userType.value = Number.isNaN(normalizedUserType) ? 0 : normalizedUserType
  profile.value = {
    ...profile.value,
    account: normalizedAccount,
    email: normalizedEmail,
    displayName: normalizedDisplayName,
  }

  persistAuthState()
}

function persistAuthState() {
  if (typeof window === 'undefined') {
    return
  }
  const payload = {
    id: userId.value,
    userType: userType.value,
    account: profile.value.account,
    email: profile.value.email,
    displayName: profile.value.displayName,
  }
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(payload))
}

function clearAuthStorage() {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.removeItem(AUTH_STORAGE_KEY)
}

function restoreAuthFromStorage() {
  if (typeof window === 'undefined') {
    return false
  }
  const saved = window.localStorage.getItem(AUTH_STORAGE_KEY)
  if (!saved) {
    return false
  }
  try {
    const parsed = JSON.parse(saved)
    if (!parsed?.id || !parsed?.email) {
      return false
    }
    userId.value = String(parsed.id)
    userType.value = Number.isNaN(Number(parsed.userType)) ? 0 : Number(parsed.userType)
    profile.value = {
      ...profile.value,
      account: parsed.account || parsed.email,
      email: parsed.email,
      displayName: parsed.displayName || profile.value.displayName || parsed.account || parsed.email,
    }
    isAuthenticated.value = true
    return true
  } catch {
    return false
  }
}
</script>

<template>
  <div v-if="!isAuthenticated" class="auth-screen">
        <div class="auth-card">
          <h1>欢迎使用 SMT 问答平台</h1>

          <div class="auth-tabs">
            <button class="auth-tab" :class="{ active: authMode === 'login' }" type="button" @click="switchAuthMode('login')">登录</button>
            <button class="auth-tab" :class="{ active: authMode === 'register' }" type="button" @click="switchAuthMode('register')">注册</button>
          </div>

          <form class="auth-form" @submit.prevent="submitAuth">
            <label class="field-label" for="auth-email">{{ authMode === 'login' ? '账号' : '邮箱' }}</label>
            <input
              id="auth-email"
              v-model="authForm.email"
              class="text-input"
              :type="authMode === 'login' ? 'text' : 'email'"
              :placeholder="authMode === 'login' ? '示例：user' : 'your.name@example.com'"
              autocomplete="email"
              required
            />

            <label class="field-label" for="auth-password">密码</label>
            <input
              id="auth-password"
              v-model="authForm.password"
              class="text-input"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
            />

            <div v-if="authMode === 'register'">
              <label class="field-label" for="auth-confirm">确认密码</label>
              <input
                id="auth-confirm"
                v-model="authForm.confirmPassword"
                class="text-input"
                type="password"
                placeholder="再次输入密码"
                autocomplete="new-password"
              />
            </div>

            <p v-if="authError" class="auth-error">{{ authError }}</p>

            <button class="primary-button auth-submit" type="submit" :disabled="isAuthenticating">
              {{ isAuthenticating ? '处理中...' : authMode === 'login' ? '立即登录' : '提交注册' }}
            </button>
          </form>
        </div>
      </div>

      <div v-else-if="isAdminRoute" class="app-shell app-shell-admin">
        <main class="workspace workspace-admin-route">
          <AdminPage :profile="profile" :user-id="userId" @back="backToChatView" />
        </main>
      </div>

      <div v-else class="chat-page-shell">
        <div class="app-shell chat-page-top">
        <aside v-if="!isAdminRoute" class="left-panel panel-card">
          <section class="history-card">
            <div class="section-title-row">
              <h2>历史记录</h2>
              <button class="ghost-button" type="button" @click="startNewSession">新建</button>
            </div>

        <p v-if="isHistoryLoading" class="history-tip">正在从数据库加载会话记录...</p>
        <p v-else-if="historyError" class="history-tip error">{{ historyError }}</p>
        <p v-else-if="!hasSessions" class="history-tip">暂无会话</p>

        <div class="history-list">
          <article
            v-for="session in sessions"
            :key="session.id"
            class="history-item"
            :class="{ active: session.id === activeSessionId }"
            tabindex="0"
            @click="switchSession(session.id)"
            @keydown.enter.prevent="switchSession(session.id)"
          >
            <span class="history-title">{{ session.title }}</span>
            <span class="history-time">{{ formatTime(session.updatedAt) }}</span>
            <button
              class="history-delete"
              type="button"
              title="删除会话"
              aria-label="删除会话"
              @click.stop="removeSession(session.id)"
              @keydown.enter.stop.prevent="removeSession(session.id)"
            >
              ×
            </button>
          </article>
        </div>
      </section>

      <section class="profile-card">
        <button class="profile-main" type="button" @click="toggleProfileMenu">
          <span class="profile-avatar" :class="{ 'profile-avatar-empty': !profile.avatar }">
            <img v-if="profile.avatar" :src="profile.avatar" alt="avatar" />
            <span v-else>{{ profileInitials }}</span>
          </span>
          <span class="profile-info">
            <strong>{{ profile.account || profile.email }}</strong>
          </span>
          <span class="profile-caret">⌄</span>
        </button>

        <div v-if="isProfileMenuOpen" class="profile-menu">
          <button type="button" @click="startPasswordEdit">修改密码</button>
          <button v-if="isAdmin" type="button" @click="openAdminView">管理</button>
          <button class="danger" type="button" @click="handleLogout">退出登录</button>
        </div>
      </section>
    </aside>

    <main class="workspace">
        <header class="workspace-header panel-card">
            <h2>{{ activeSession?.title ?? '暂无会话' }}</h2>
        </header>

        <section v-if="hasSessions && requestExamples.length" class="example-strip">
          <button v-for="example in requestExamples" :key="example" class="example-chip" type="button" @click="fillExample(example)">
            {{ example }}
          </button>
        </section>

        <section ref="transcriptRef" class="transcript panel-card" :class="{ 'transcript-empty': !hasSessions }">
          <div v-if="!hasSessions" class="empty-state chat-empty-state">
            <p>暂无会话，请点击“新建”开始对话。</p>
            <button class="primary-button empty-action" type="button" @click="startNewSession">新建会话</button>
          </div>

          <article
            v-for="message in activeMessages"
            v-else
            :key="message.id"
            class="message-row"
            :class="[message.role, { selected: isSelectedSystemMessage(message) }]"
          >
            <div class="message-marker">{{ message.role === 'user' ? 'Q' : 'R' }}</div>
            <div
              class="message-card"
              :class="{ 'message-card-selectable': message.role === 'assistant' }"
              :tabindex="message.role === 'assistant' ? 0 : undefined"
              @click="selectSystemMessage(message)"
              @keydown.enter.prevent="selectSystemMessage(message)"
            >
              <div class="message-meta">
                <strong v-if="message.role !== 'user'">
                  {{ message.replyKind === 'optimize' ? '后端优化结果' : '后端求解结果' }}
                </strong>
                <span>{{ formatTime(message.createdAt) }}</span>
              </div>
              <pre v-if="message.replyKind !== 'optimize'" class="message-content">{{ message.content }}</pre>

              <section v-if="message.sections.length" class="detail-section">
                <div v-for="section in message.sections" :key="section.label" class="detail-card">
                  <h3>{{ section.label }}</h3>
                  <pre>{{ section.content }}</pre>
                </div>
              </section>

              <div v-if="message.replyKind !== 'optimize' && canOptimizeMessage(message)" class="message-actions">
                <button class="ghost-button" type="button" @click.stop="optimizeMessage(message)">
                  {{ isOptimizingCode && selectedOptimizeMessage?.id === message.id ? '优化中...' : '优化' }}
                </button>
              </div>

              <section
                v-if="message.replyKind === 'optimize' && (message.smtCode || canOptimizeMessage(message))"
                class="code-block"
              >
                <div class="code-header">
                  <span>SMT CODE</span>
                  <div class="message-actions code-actions">
                    <button class="ghost-button" type="button" @click.stop="optimizeMessage(message)">
                      {{ isOptimizingCode && selectedOptimizeMessage?.id === message.id ? '优化中...' : '优化' }}
                    </button>
                    <button v-if="canCompareOptimize(message)" class="ghost-button" type="button" @click.stop="openOptimizeCompare(message)">
                      对比
                    </button>
                    <button v-if="message.smtCode" class="ghost-button" type="button" @click.stop="copyText(message.smtCode)">
                      复制代码
                    </button>
                    <button v-if="canDeleteOptimize(message)" class="ghost-button danger-button" type="button" @click.stop="deleteOptimizeMessage(message)">
                      删除
                    </button>
                  </div>
                </div>
                <pre class="formal-code">{{ message.smtCode || '暂无代码内容' }}</pre>
              </section>

              <details v-if="message.rawPayload" class="raw-payload">
                <summary>查看原始响应</summary>
                <pre>{{ message.rawPayload }}</pre>
              </details>
            </div>
          </article>

          <div v-if="isLoading" class="loading-card">
            <span class="loader-dot" />
            正在等待后端求解并返回结果...
          </div>
        </section>

        <footer v-if="hasSessions" class="composer panel-card">
          <div class="composer-field">
            <textarea
              id="question"
              v-model="inputText"
              class="composer-input"
              placeholder="输入你的问题"
              @keydown.enter.exact.prevent="submitQuestion"
            />
            <button class="primary-button composer-submit" type="button" :disabled="isLoading || !inputText.trim()" @click="submitQuestion">
              提交给后端
            </button>
          </div>
        </footer>
    </main>
        </div>

        <section class="page-reference-shell">
          <section class="panel-card inspector-card">
            <div class="tab-row">
              <button class="tab-button" :class="{ active: activeReferenceTab === 'glossary' }" type="button" @click="activeReferenceTab = 'glossary'">
                SMT 基础
              </button>
              <button class="tab-button" :class="{ active: activeReferenceTab === 'contract' }" type="button" @click="activeReferenceTab = 'contract'">
                接口约定
              </button>
            </div>

            <div v-if="activeReferenceTab === 'glossary'" class="glossary-grid">
              <article v-for="item in smtGlossary" :key="item.keyword" class="glossary-card">
                <div class="glossary-head">
                  <strong>{{ item.keyword }}</strong>
                  <span>{{ item.category }}</span>
                </div>
                <p>{{ item.description }}</p>
                <pre>{{ item.example }}</pre>
              </article>
            </div>

            <div v-else class="contract-panel">
              <div class="detail-card">
                <h3>聊天请求</h3>
                <pre>POST /api/qa/chat
{
  "question": "自然语言问题",
  "input": "自然语言问题",
  "inputType": "natural_language",
  "conversationId": "string",
  "history": [{ "role": "user", "content": "..." }],
  "options": {
    "returnSmtCode": true,
    "includeModel": true,
    "includeExplanation": true
  }
}</pre>
              </div>

              <div class="detail-card">
                <h3>历史记录接口</h3>
                <pre>GET /api/qa/conversations
GET /api/qa/conversations/{conversationId}
DELETE /api/qa/conversations/{conversationId}</pre>
              </div>

              <div class="detail-card">
                <h3>历史记录响应建议</h3>
                <pre>{
  "conversations": [
    {
      "conversationId": "conv-001",
      "title": "整数约束求解",
      "updatedAt": "2026-03-22T10:00:00Z"
    }
  ]
}</pre>
              </div>
            </div>
          </section>

          <section class="panel-card code-preview-card">
            <div class="section-title-row">
              <h2>当前 SMT 输出</h2>
              <button class="ghost-button" type="button" :disabled="!activeSmtCode" @click="copyText(activeSmtCode)">复制</button>
            </div>

            <pre v-if="activeSmtCode" class="formal-code compact">{{ activeSmtCode }}</pre>
            <div v-else class="empty-state">
              这里会优先展示当前系统回答中的 SMT 代码；如果后端暂时只返回求解结果文本，也会同步展示最新系统回答。
            </div>
          </section>
        </section>
      </div>

      <div v-if="isProfileDialogOpen" class="profile-dialog-backdrop" @click.self="closeProfileDialog">
        <div class="profile-dialog">
          <h2>修改密码</h2>
          <label class="field-label" for="new-password">新密码</label>
          <input
            id="new-password"
            v-model="passwordForm.newPassword"
            class="text-input"
            type="password"
            placeholder="请输入新密码"
          />

          <label class="field-label" for="confirm-new-password">确认新密码</label>
          <input
            id="confirm-new-password"
            v-model="passwordForm.confirmPassword"
            class="text-input"
            type="password"
            placeholder="请再次输入新密码"
          />

          <p v-if="passwordError" class="auth-error">{{ passwordError }}</p>

          <div class="dialog-actions">
            <button class="ghost-button" type="button" :disabled="isPasswordUpdating" @click="closeProfileDialog">取消</button>
            <button class="primary-button" type="button" :disabled="isPasswordUpdating" @click="savePassword">
              {{ isPasswordUpdating ? '提交中...' : '确认修改' }}
            </button>
          </div>
        </div>
      </div>

  <el-drawer
    v-model="optimizeDrawerVisible"
    title="系统求解结果代码对比"
    direction="rtl"
    :size="optimizeDrawerSize"
    :teleported="false"
    class="optimize-records-drawer"
  >
    <div class="optimize-records-shell">
      <div
        class="optimize-drawer-resizer"
        :class="{ active: isResizingOptimizeDrawer }"
        @pointerdown.prevent="beginOptimizeDrawerResize"
      />
      <div class="optimize-records-content optimize-records-compare-only">
        <div v-if="optimizeRecordsLoading" class="loading-card optimize-records-loading">
          <span class="loader-dot" />
          正在加载优化记录...
        </div>

        <p v-else-if="optimizeRecordsError" class="history-tip error">{{ optimizeRecordsError }}</p>

        <div v-else class="optimize-compare-layout">
          <section class="detail-card optimize-compare-panel">
            <div class="optimize-record-head">
              <strong>原始代码</strong>
              <span v-if="selectedCompareRecord">
                {{ selectedCompareRecord.createTime ? formatTime(selectedCompareRecord.createTime) : '无时间信息' }}
              </span>
            </div>
            <pre>{{ compareOriginalCode || '当前系统回答暂无可展示的原始代码。' }}</pre>
          </section>

          <section class="detail-card optimize-compare-panel">
            <div class="optimize-record-head">
              <strong>优化代码</strong>
              <span v-if="selectedCompareRecord">
                {{ selectedCompareRecord.createTime ? formatTime(selectedCompareRecord.createTime) : '无时间信息' }}
              </span>
            </div>
            <pre>{{ compareOptimizedCode || '当前系统回答还没有优化记录，请先点击“优化”。' }}</pre>
          </section>
        </div>
      </div>
    </div>
  </el-drawer>
</template>


