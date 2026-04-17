<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from '../../axiosInstance.js'

const props = defineProps({
  profile: {
    type: Object,
    required: true,
  },
  userId: {
    type: [String, Number],
    default: '',
  },
})

const emit = defineEmits(['back'])

const activeMenu = ref('users')
const userLoading = ref(false)
const userError = ref('')
const users = ref([])
const sessionLoading = ref(false)
const sessionError = ref('')
const sessions = ref([])
const historyLoading = ref(false)
const historyError = ref('')
const optimizeRecords = ref([])
const codeDetailVisible = ref(false)
const selectedOptimizeRecord = ref(null)

const paginationSizes = [5, 10, 30]
const userPage = ref(1)
const userPageSize = ref(5)
const sessionPage = ref(1)
const sessionPageSize = ref(5)
const historyPage = ref(1)
const historyPageSize = ref(5)

const USERS_API = '/users'
const DELETE_USER_API = '/deleteUser'
const ALL_SESSIONS_API = '/allSessions'
const DELETE_SESSION_API = '/delete'
const OPTIMIZE_RECORDS_API = '/optimizeRecords'
const DELETE_OPTIMIZE_RECORD_API = '/deleteOptimizeRecord'

const text = {
  pageTitle: '\u540e\u53f0\u7ba1\u7406\u7cfb\u7edf',
  backText: '\u8fd4\u56de\u4f1a\u8bdd',
  accountLabel: '\u5f53\u524d\u7ba1\u7406\u5458',
  idLabel: 'ID',
  users: '\u7528\u6237\u4fe1\u606f\u7ba1\u7406',
  sessions: '\u4f1a\u8bdd\u6570\u636e\u7ba1\u7406',
  history: '\u5386\u53f2\u8bb0\u5f55\u7ef4\u62a4',
  userPanelTitle: '\u7528\u6237\u4fe1\u606f\u7ba1\u7406',
  sessionPanelTitle: '\u4f1a\u8bdd\u6570\u636e\u7ba1\u7406',
  historyPanelTitle: '\u5386\u53f2\u8bb0\u5f55\u7ef4\u62a4',
  refreshText: '\u5237\u65b0\u5217\u8868',
  archiveConfigText: '\u5f52\u6863\u914d\u7f6e',
  cleanNowText: '\u7acb\u5373\u6e05\u7406',
  userEmptyText: '\u6682\u65e0\u7528\u6237\u6570\u636e',
  sessionEmptyText: '\u6682\u65e0\u4f1a\u8bdd\u6570\u636e',
  userEmail: '\u90ae\u7bb1',
  userPassword: '\u5bc6\u7801',
  userRole: '\u89d2\u8272',
  userStatus: '\u72b6\u6001',
  userCreateTime: '\u521b\u5efa\u65f6\u95f4',
  userAction: '\u64cd\u4f5c',
  userDelete: '\u5220\u9664',
  sessionUserId: '\u7528\u6237ID',
  sessionTitle: '\u4f1a\u8bdd\u4e3b\u9898',
  sessionLastMessage: '\u6700\u540e\u4e00\u6761\u6d88\u606f',
  sessionUpdateTime: '\u66f4\u65b0\u65f6\u95f4',
  sessionAction: '\u64cd\u4f5c',
  sessionDelete: '\u5220\u9664',
  historyOptId: '\u4f18\u5316ID',
  historyMessageId: 'Message ID',
  historyOriginalCode: '\u539f\u59cb\u4ee3\u7801',
  historyOptimizedCode: '\u4f18\u5316\u540e\u4ee3\u7801',
  historyCreateTime: '\u521b\u5efa\u65f6\u95f4',
  historyEmptyText: '\u6682\u65e0\u4f18\u5316\u8bb0\u5f55',
  historyDetail: '\u4ee3\u7801\u8be6\u60c5',
  historyAction: '\u64cd\u4f5c',
  historyDelete: '\u5220\u9664',
  historyOriginalPanel: '\u539f\u59cb\u4ee3\u7801',
  historyOptimizedPanel: '\u4f18\u5316\u540e\u4ee3\u7801',
  statusNormal: '\u6b63\u5e38',
  statusDeleted: '\u5df2\u5220\u9664',
  roleAdmin: '\u7ba1\u7406\u5458',
  roleUser: '\u666e\u901a\u7528\u6237',
}

const currentAdminAccount = computed(() => props.profile.account || props.profile.email || '-')

const userRows = computed(() =>
  users.value.map((user) => ({
    id: user.id ?? '-',
    email: user.email || '-',
    password: user.password || '-',
    role: Number(user.userType ?? user.user_type ?? 0) === 1 ? text.roleAdmin : text.roleUser,
    status: text.statusNormal,
    createTime: user.createTime || user.create_time || '-',
  })),
)

const sessionRows = computed(() =>
  sessions.value
    .filter((session) => Number(session.deleted ?? session.isDeleted ?? session.is_deleted ?? 0) !== 1)
    .map((session) => ({
      id: session.id ?? '-',
      userId: session.userId ?? session.user_id ?? '-',
      title: session.title || '-',
      lastMessage: session.lastMessage || session.last_message || '-',
      updateTime: session.updateTime || session.update_time || session.createTime || session.create_time || '-',
      status: text.statusNormal,
    })),
)

const historyRows = computed(() =>
  optimizeRecords.value.map((record) => ({
    optId: record.optId ?? record.opt_id ?? '-',
    messageId: record.messageId ?? record.message_id ?? '-',
    originalCode: record.originalCode || record.original_code || '-',
    optimizedCode: record.optimizedCode || record.optimized_code || '-',
    createTime: record.createTime || record.create_time || '-',
  })),
)

function handleMenuSelect(index) {
  activeMenu.value = index
}

function openCodeDetail(row) {
  selectedOptimizeRecord.value = row
  codeDetailVisible.value = true
}

function paginateRows(rows, page, pageSize) {
  const start = (page - 1) * pageSize
  return rows.slice(start, start + pageSize)
}

const pagedUserRows = computed(() => paginateRows(userRows.value, userPage.value, userPageSize.value))
const pagedSessionRows = computed(() =>
  paginateRows(sessionRows.value, sessionPage.value, sessionPageSize.value),
)
const pagedHistoryRows = computed(() =>
  paginateRows(historyRows.value, historyPage.value, historyPageSize.value),
)

function handleUserPageSizeChange(size) {
  userPageSize.value = size
  userPage.value = 1
}

function handleSessionPageSizeChange(size) {
  sessionPageSize.value = size
  sessionPage.value = 1
}

function handleHistoryPageSizeChange(size) {
  historyPageSize.value = size
  historyPage.value = 1
}

onMounted(() => {
  fetchUsers()
  fetchSessions()
  fetchOptimizeRecords()
})

async function fetchUsers() {
  userLoading.value = true
  userError.value = ''

  try {
    const response = await axios.get(USERS_API)
    const body = response?.data ?? null

    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code !== 200) {
        throw new Error(body.message || '\u7528\u6237\u5217\u8868\u52a0\u8f7d\u5931\u8d25')
      }
      users.value = Array.isArray(body.data) ? body.data : []
      userPage.value = 1
      return
    }

    users.value = Array.isArray(body) ? body : []
    userPage.value = 1
  } catch (error) {
    userError.value = error instanceof Error ? error.message : '\u7528\u6237\u5217\u8868\u52a0\u8f7d\u5931\u8d25'
    users.value = []
    userPage.value = 1
  } finally {
    userLoading.value = false
  }
}

async function handleDeleteUser(row) {
  if (!row?.id || row.id === '-') {
    ElMessage.error('\u672a\u83b7\u53d6\u5230\u53ef\u5220\u9664\u7684\u7528\u6237ID')
    return
  }

  try {
    await ElMessageBox.confirm(
      `\u786e\u8ba4\u5220\u9664\u7528\u6237 ${row.email || row.id} \u5417\uff1f`,
      '\u5220\u9664\u786e\u8ba4',
      {
        confirmButtonText: '\u786e\u8ba4\u5220\u9664',
        cancelButtonText: '\u53d6\u6d88',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  try {
    const formData = new URLSearchParams()
    formData.append('id', String(row.id))

    const response = await axios.post(DELETE_USER_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const body = response?.data ?? null
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      throw new Error(body.message || '\u5220\u9664\u7528\u6237\u5931\u8d25')
    }

    ElMessage.success('\u7528\u6237\u5df2\u5220\u9664')
    await fetchUsers()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '\u5220\u9664\u7528\u6237\u5931\u8d25')
  }
}

async function fetchSessions() {
  sessionLoading.value = true
  sessionError.value = ''

  try {
    const response = await axios.get(ALL_SESSIONS_API)
    const body = response?.data ?? null

    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code !== 200) {
        throw new Error(body.message || '\u4f1a\u8bdd\u5217\u8868\u52a0\u8f7d\u5931\u8d25')
      }
      sessions.value = Array.isArray(body.data) ? body.data : []
      sessionPage.value = 1
      return true
    }

    sessions.value = Array.isArray(body) ? body : []
    sessionPage.value = 1
    return true
  } catch (error) {
    sessionError.value = error instanceof Error ? error.message : '\u4f1a\u8bdd\u5217\u8868\u52a0\u8f7d\u5931\u8d25'
    sessions.value = []
    sessionPage.value = 1
    return false
  } finally {
    sessionLoading.value = false
  }
}

async function handleRefreshSessions() {
  const success = await fetchSessions()

  if (success) {
    ElMessage.success('\u4f1a\u8bdd\u5217\u8868\u5df2\u5237\u65b0')
    return
  }

  ElMessage.error(sessionError.value || '\u4f1a\u8bdd\u5217\u8868\u5237\u65b0\u5931\u8d25')
}

async function handleDeleteSession(row) {
  if (!row?.id || row.id === '-') {
    ElMessage.error('\u672a\u83b7\u53d6\u5230\u53ef\u5220\u9664\u7684\u4f1a\u8bddID')
    return
  }

  try {
    await ElMessageBox.confirm(
      `\u786e\u8ba4\u5220\u9664\u4f1a\u8bdd\u300c${row.title || row.id}\u300d\u5417\uff1f`,
      '\u5220\u9664\u786e\u8ba4',
      {
        confirmButtonText: '\u786e\u8ba4\u5220\u9664',
        cancelButtonText: '\u53d6\u6d88',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  try {
    const formData = new URLSearchParams()
    formData.append('sessionId', String(row.id))

    const response = await axios.post(DELETE_SESSION_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const body = response?.data ?? null
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      throw new Error(body.message || '\u5220\u9664\u4f1a\u8bdd\u5931\u8d25')
    }

    ElMessage.success('\u4f1a\u8bdd\u5df2\u5220\u9664')
    await fetchSessions()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '\u5220\u9664\u4f1a\u8bdd\u5931\u8d25')
  }
}

async function fetchOptimizeRecords() {
  historyLoading.value = true
  historyError.value = ''

  try {
    const response = await axios.get(OPTIMIZE_RECORDS_API)
    const body = response?.data ?? null

    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code !== 200) {
        throw new Error(body.message || '\u4f18\u5316\u8bb0\u5f55\u52a0\u8f7d\u5931\u8d25')
      }
      optimizeRecords.value = Array.isArray(body.data) ? body.data : []
      historyPage.value = 1
      return true
    }

    optimizeRecords.value = Array.isArray(body) ? body : []
    historyPage.value = 1
    return true
  } catch (error) {
    historyError.value = error instanceof Error ? error.message : '\u4f18\u5316\u8bb0\u5f55\u52a0\u8f7d\u5931\u8d25'
    optimizeRecords.value = []
    historyPage.value = 1
    return false
  } finally {
    historyLoading.value = false
  }
}

async function handleRefreshOptimizeRecords() {
  const success = await fetchOptimizeRecords()

  if (success) {
    ElMessage.success('\u4f18\u5316\u8bb0\u5f55\u5df2\u5237\u65b0')
    return
  }

  ElMessage.error(historyError.value || '\u4f18\u5316\u8bb0\u5f55\u5237\u65b0\u5931\u8d25')
}

async function handleDeleteOptimizeRecord(row) {
  if (!row?.optId || row.optId === '-') {
    ElMessage.error('\u672a\u83b7\u53d6\u5230\u53ef\u5220\u9664\u7684\u4f18\u5316\u8bb0\u5f55ID')
    return
  }

  try {
    await ElMessageBox.confirm(
      `\u786e\u8ba4\u5220\u9664\u4f18\u5316\u8bb0\u5f55 #${row.optId} \u5417\uff1f`,
      '\u5220\u9664\u786e\u8ba4',
      {
        confirmButtonText: '\u786e\u8ba4\u5220\u9664',
        cancelButtonText: '\u53d6\u6d88',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  try {
    const formData = new URLSearchParams()
    formData.append('optId', String(row.optId))

    const response = await axios.post(DELETE_OPTIMIZE_RECORD_API, formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    })

    const body = response?.data ?? null
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      throw new Error(body.message || '\u5220\u9664\u4f18\u5316\u8bb0\u5f55\u5931\u8d25')
    }

    ElMessage.success('\u4f18\u5316\u8bb0\u5f55\u5df2\u5220\u9664')
    await fetchOptimizeRecords()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '\u5220\u9664\u4f18\u5316\u8bb0\u5f55\u5931\u8d25')
  }
}
</script>

<template>
  <div class="admin-page-shell admin-element-shell">
    <el-container class="admin-layout">
      <el-header class="admin-layout-header">
        <div class="admin-header-content">
          <div class="admin-header-copy">
            <h2>{{ text.pageTitle }}</h2>
          </div>
          <div class="admin-header-actions">
            <span class="admin-account-chip">{{ text.idLabel }}: {{ props.userId || '-' }}</span>
            <span class="admin-account-chip">{{ text.accountLabel }}: {{ currentAdminAccount }}</span>
            <el-button type="primary" plain @click="emit('back')">{{ text.backText }}</el-button>
          </div>
        </div>
      </el-header>

      <el-container class="admin-layout-body">
        <el-aside width="188px" class="admin-layout-aside">
          <div class="admin-aside-brand">
            <strong>{{ text.pageTitle }}</strong>
          </div>

          <el-menu
            :default-active="activeMenu"
            class="admin-side-menu"
            background-color="#545c64"
            text-color="#ffffff"
            active-text-color="#ffd04b"
            @select="handleMenuSelect"
          >
            <el-menu-item index="users">
              <span class="admin-menu-icon">U</span>
              <span>{{ text.users }}</span>
            </el-menu-item>
            <el-menu-item index="sessions">
              <span class="admin-menu-icon">S</span>
              <span>{{ text.sessions }}</span>
            </el-menu-item>
            <el-menu-item index="history">
              <span class="admin-menu-icon">H</span>
              <span>{{ text.history }}</span>
            </el-menu-item>
          </el-menu>
        </el-aside>

        <el-main class="admin-layout-main">
          <el-card v-if="activeMenu === 'users'" shadow="never" class="admin-content-card">
            <template #header>
              <div class="admin-card-head">
                <span>{{ text.userPanelTitle }}</span>
                <div class="admin-card-actions">
                  <el-button size="small" @click="fetchUsers">{{ text.refreshText }}</el-button>
                </div>
              </div>
            </template>

            <el-alert
              v-if="userError"
              :title="userError"
              type="error"
              show-icon
              :closable="false"
              class="admin-alert"
            />

            <div class="admin-table-scroll">
              <el-table :data="pagedUserRows" stripe v-loading="userLoading" :empty-text="text.userEmptyText">
                <el-table-column prop="id" label="ID" width="90" />
                <el-table-column prop="email" :label="text.userEmail" />
                <el-table-column prop="password" :label="text.userPassword" min-width="140" />
                <el-table-column prop="role" :label="text.userRole" />
                <el-table-column prop="status" :label="text.userStatus" />
                <el-table-column prop="createTime" :label="text.userCreateTime" min-width="180" />
                <el-table-column :label="text.userAction" width="110" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" type="danger" plain @click="handleDeleteUser(row)">
                      {{ text.userDelete }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="admin-pagination">
              <el-pagination
                background
                layout="total, sizes, prev, pager, next"
                :total="userRows.length"
                :page-sizes="paginationSizes"
                :page-size="userPageSize"
                :current-page="userPage"
                @size-change="handleUserPageSizeChange"
                @current-change="(page) => (userPage = page)"
              />
            </div>
          </el-card>

          <el-card v-else-if="activeMenu === 'sessions'" shadow="never" class="admin-content-card">
            <template #header>
              <div class="admin-card-head">
                <span>{{ text.sessionPanelTitle }}</span>
                <div class="admin-card-actions">
                  <el-button size="small" @click="handleRefreshSessions">{{ text.refreshText }}</el-button>
                </div>
              </div>
            </template>

            <el-alert
              v-if="sessionError"
              :title="sessionError"
              type="error"
              show-icon
              :closable="false"
              class="admin-alert"
            />

            <div class="admin-table-scroll">
              <el-table
                :data="pagedSessionRows"
                stripe
                v-loading="sessionLoading"
                :empty-text="text.sessionEmptyText"
              >
                <el-table-column prop="id" label="ID" width="90" />
                <el-table-column prop="userId" :label="text.sessionUserId" width="110" />
                <el-table-column prop="title" :label="text.sessionTitle" min-width="180" />
                <el-table-column prop="lastMessage" :label="text.sessionLastMessage" min-width="220" />
                <el-table-column prop="updateTime" :label="text.sessionUpdateTime" min-width="180" />
                <el-table-column prop="status" :label="text.userStatus" width="110" />
                <el-table-column :label="text.sessionAction" width="110" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" type="danger" plain @click="handleDeleteSession(row)">
                      {{ text.sessionDelete }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="admin-pagination">
              <el-pagination
                background
                layout="total, sizes, prev, pager, next"
                :total="sessionRows.length"
                :page-sizes="paginationSizes"
                :page-size="sessionPageSize"
                :current-page="sessionPage"
                @size-change="handleSessionPageSizeChange"
                @current-change="(page) => (sessionPage = page)"
              />
            </div>
          </el-card>

          <el-card v-else shadow="never" class="admin-content-card">
            <template #header>
              <div class="admin-card-head">
                <span>{{ text.historyPanelTitle }}</span>
                <div class="admin-card-actions">
                  <el-button size="small" @click="handleRefreshOptimizeRecords">{{ text.refreshText }}</el-button>
                </div>
              </div>
            </template>

            <el-alert
              v-if="historyError"
              :title="historyError"
              type="error"
              show-icon
              :closable="false"
              class="admin-alert"
            />

            <div class="admin-table-scroll">
              <el-table
                :data="pagedHistoryRows"
                stripe
                v-loading="historyLoading"
                :empty-text="text.historyEmptyText"
              >
                <el-table-column prop="optId" :label="text.historyOptId" width="110" />
                <el-table-column prop="messageId" :label="text.historyMessageId" width="120" />
                <el-table-column prop="originalCode" :label="text.historyOriginalCode" min-width="240" show-overflow-tooltip />
                <el-table-column prop="optimizedCode" :label="text.historyOptimizedCode" min-width="240" show-overflow-tooltip />
                <el-table-column prop="createTime" :label="text.historyCreateTime" min-width="180" />
                <el-table-column :label="text.historyAction" width="190" fixed="right">
                  <template #default="{ row }">
                    <div class="admin-card-actions">
                      <el-button size="small" type="primary" plain @click="openCodeDetail(row)">
                        {{ text.historyDetail }}
                      </el-button>
                      <el-button size="small" type="danger" plain @click="handleDeleteOptimizeRecord(row)">
                        {{ text.historyDelete }}
                      </el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="admin-pagination">
              <el-pagination
                background
                layout="total, sizes, prev, pager, next"
                :total="historyRows.length"
                :page-sizes="paginationSizes"
                :page-size="historyPageSize"
                :current-page="historyPage"
                @size-change="handleHistoryPageSizeChange"
                @current-change="(page) => (historyPage = page)"
              />
            </div>
          </el-card>
        </el-main>
      </el-container>
    </el-container>

    <el-drawer
      v-model="codeDetailVisible"
      :title="text.historyDetail"
      direction="rtl"
      size="42%"
      class="admin-code-drawer"
    >
      <div v-if="selectedOptimizeRecord" class="admin-code-detail">
        <div class="admin-code-meta">
          <span class="admin-account-chip">{{ text.historyOptId }}: {{ selectedOptimizeRecord.optId }}</span>
          <span class="admin-account-chip">{{ text.historyMessageId }}: {{ selectedOptimizeRecord.messageId }}</span>
        </div>

        <section class="admin-code-panel">
          <h3>{{ text.historyOriginalPanel }}</h3>
          <pre>{{ selectedOptimizeRecord.originalCode }}</pre>
        </section>

        <section class="admin-code-panel">
          <h3>{{ text.historyOptimizedPanel }}</h3>
          <pre>{{ selectedOptimizeRecord.optimizedCode }}</pre>
        </section>
      </div>
    </el-drawer>
  </div>
</template>
