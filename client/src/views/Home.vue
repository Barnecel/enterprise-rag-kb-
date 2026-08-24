<template>
  <div class="home-container">
    <!-- 顶部导航栏（Apple 风：固定 + 毛玻璃 + 居中文字导航） -->
    <header class="topbar">
      <div class="nav-inner">
        <!-- 左区：品牌（HIG：工具栏单层三段式，杜绝绝对定位导致的重叠） -->
        <div class="nav-side nav-side--left">
          <div class="brand" @click="go('/chat')" title="回到智能问答">
            <span class="mark">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L19.7 10l-5.8 1.9L12 17.7l-1.9-5.8L4.3 10l5.8-1.2z"/></svg>
            </span>
            <span class="brand-name">企业知识库</span>
          </div>
        </div>

        <!-- 中区：核心导航（flex:none，两侧弹性轨道保证最小间隔） -->
        <nav class="nav-links">
            <template v-for="item in navItems" :key="item.path">
              <!-- 管理后台聚合下拉（HIG：工具栏只保留核心项，次要功能收进菜单） -->
              <el-dropdown v-if="item.children" trigger="hover" @command="go">
                <button class="nav-link" :class="{ active: isActive(item) }">
                  {{ item.label }}
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="c in item.children"
                      :key="c.path"
                      :command="c.path"
                      :class="{ 'is-current': route.path.startsWith(c.path) }"
                    >{{ c.label }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <button
                v-else
                class="nav-link"
                :class="{ active: isActive(item) }"
                @click="go(item.path)"
              >{{ item.label }}</button>
            </template>
          </nav>

        <!-- 右区：主题 + 用户 + 汉堡（与左区同一弹性布局层，天然保证间隔） -->
        <div class="nav-side nav-side--right">
          <div class="theme-switch" title="主题：自动跟随时间">
            <button :class="{ on: themePref === 'auto' }" @click="setTheme('auto')">
              <el-icon :size="15"><Clock /></el-icon><span>自动</span>
            </button>
            <button :class="{ on: themePref === 'light' }" @click="setTheme('light')" title="浅色">
              <el-icon :size="15"><Sunny /></el-icon>
            </button>
            <button :class="{ on: themePref === 'dark' }" @click="setTheme('dark')" title="深色">
              <el-icon :size="15"><Moon /></el-icon>
            </button>
          </div>

          <el-dropdown @command="handleCommand">
            <div class="user-chip">
              <span class="avatar">{{ avatarText }}</span>
              <span class="username">{{ userInfo.real_name || userInfo.username }}</span>
              <span class="role-tag" :class="userInfo.role">{{ userInfo.role === 'admin' ? '管理员' : '用户' }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <button class="hamburger" aria-label="菜单" @click="mobileMenuOpen = true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
        </div>
      </div>
    </header>

    <!-- Apple 式全屏菜单（<1100px） -->
    <transition name="menu-fade">
      <div v-if="mobileMenuOpen" class="mobile-menu">
        <button class="mobile-menu-close" aria-label="关闭菜单" @click="mobileMenuOpen = false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
        <div class="mobile-menu-brand">
          <span class="mark">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L19.7 10l-5.8 1.9L12 17.7l-1.9-5.8L4.3 10l5.8-1.2z"/></svg>
          </span>
          <span>企业知识库</span>
        </div>
        <nav class="mobile-menu-links">
          <button
            v-for="item in mobileItems"
            :key="item.path"
            class="mobile-menu-link"
            :class="{ active: isActive(item) }"
            @click="go(item.path)"
          >{{ item.label }}</button>
        </nav>
        <div class="mobile-menu-user">
          <span class="avatar">{{ avatarText }}</span>
          <span>{{ userInfo.real_name || userInfo.username }}</span>
          <span class="role-tag" :class="userInfo.role">{{ userInfo.role === 'admin' ? '管理员' : '用户' }}</span>
        </div>
      </div>
    </transition>

    <!-- 内容区域 -->
    <div class="main-container">
      <main class="content" :class="{ 'content--flush': route.path === '/chat' }">
        <!-- keep-alive 缓存 Chat/Document：切换页面后聊天记录、流式回答、批量上传进度条不丢失 -->
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <keep-alive :include="['Chat', 'Document']">
              <component :is="Component" :key="route.path" />
            </keep-alive>
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Clock, Sunny, Moon } from '@element-plus/icons-vue'
import { getThemePreference, setThemePreference } from '../utils/theme'

const router = useRouter()
const route = useRoute()

const userInfo = ref({
  id: 0,
  username: '',
  real_name: '',
  role: 'user'
})

// Apple 全屏菜单开关（<1100px）
const mobileMenuOpen = ref(false)

const themePref = ref(getThemePreference())
const setTheme = (mode) => {
  setThemePreference(mode)
  themePref.value = mode
}

const avatarText = computed(() => {
  const name = userInfo.value.real_name || userInfo.value.username
  return name ? name.slice(0, 1).toUpperCase() : 'U'
})

// 顶部导航项（HIG：核心项平铺，管理类功能聚合为一个下拉，避免顶栏拥挤重叠）
const baseNav = [
  { label: '智能问答', path: '/chat' },
  { label: '知识库', path: '/document' }
]
const adminGroup = {
  label: '管理后台',
  path: '/admin',
  children: [
    { label: '控制台', path: '/admin/dashboard' },
    { label: '用户管理', path: '/admin/users' },
    { label: '文档管理', path: '/admin/documents' },
    { label: '分类管理', path: '/admin/categories' },
    { label: '模型接入', path: '/admin/models' },
    { label: '反馈统计', path: '/admin/feedback' },
    { label: '登录日志', path: '/admin/logs' }
  ]
}
const navItems = computed(() => {
  const items = [...baseNav]
  if (userInfo.value.role === 'admin') items.push(adminGroup)
  return items
})
// 窄屏全屏菜单：下拉组拍平为一级列表（移动端无悬停，直接铺开更符合触摸交互）
const mobileItems = computed(() => {
  const flat = []
  for (const it of navItems.value) {
    if (it.children) flat.push(...it.children)
    else flat.push(it)
  }
  return flat
})

// active 判定：/chat 精确匹配，其余前缀匹配；管理组任一子页激活即高亮
const isActive = (item) => {
  if (item.path === '/chat') {
    return route.path === item.path
  }
  return route.path.startsWith(item.path)
}

onMounted(() => {
  const stored = localStorage.getItem('userInfo')
  if (stored) {
    try {
      userInfo.value = JSON.parse(stored)
    } catch (e) {
      console.error('Failed to parse user info:', e)
    }
  }
})

const go = (path) => {
  mobileMenuOpen.value = false
  router.push(path)
}

const handleCommand = (command) => {
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      router.push('/login')
    }).catch(() => {})
  } else if (command === 'profile') {
    mobileMenuOpen.value = false
    router.push('/profile')
  }
}
</script>

<style scoped>
.home-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

/* ===== 顶部导航栏：固定 + 毛玻璃（Apple 风） ===== */
.topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  z-index: 100;
  background: var(--topbar);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--border);
}
.nav-inner {
  position: relative;
  height: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 var(--space-6);
  display: flex;
  align-items: center;
}

/* 三段式单层布局：两侧等宽弹性轨道把中间导航"顶"在正中，
   右区控件回归文档流——与导航之间永远隔着弹性空间，物理上不可能重叠 */
.nav-side {
  flex: 1 1 0;
  min-width: 96px;      /* 保证最小呼吸间隔 */
  display: flex;
  align-items: center;
}
.nav-side--right {
  justify-content: flex-end;
  gap: var(--space-4);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.brand .mark {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--grad-mark);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 4px 12px rgba(0, 113, 227, .3);
}
.brand-name {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--text);
}

/* 居中文字导航链接（Apple 风）：flex:none 保持内容宽，两侧留出固定呼吸边距 */
.nav-links {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex: none;
  margin-inline: var(--space-5); /* 与左/右区的最小间隔 */
}
.nav-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 38px; /* HIG：保证足够的点击热区 */
  border: none;
  background: transparent;
  font-family: inherit;
  font-size: 13.5px;
  color: var(--text2);
  padding: 6px var(--space-3);
  border-radius: 8px;
  cursor: pointer;
  transition: color .15s;
}
.nav-link svg { opacity: .55; transition: transform .18s, opacity .15s; }
.nav-link:hover svg { opacity: .9; }
.el-dropdown:hover :deep(.nav-link svg),
.el-dropdown:focus-visible :deep(.nav-link svg) { transform: rotate(180deg); }
.nav-link:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
.nav-link:hover { color: var(--text); }
.nav-link.active {
  color: var(--text);
  font-weight: 600;
}
.nav-link.active::after {
  content: '';
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  bottom: 1px;
  width: 20px;
  height: 2.5px;
  border-radius: 2px;
  background: var(--primary);
}

/* 汉堡按钮：<1100px 显示 */
.hamburger {
  display: none;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: var(--bg);
  color: var(--text2);
  cursor: pointer;
  transition: background .18s, color .18s;
}
.hamburger:hover { background: var(--hover); color: var(--text); }

/* 主题切换 */
.theme-switch {
  display: flex;
  align-items: center;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 980px;
  padding: 3px;
}
.theme-switch button {
  display: flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: transparent;
  color: var(--text2);
  font-size: 12.5px;
  font-family: inherit;
  padding: 5px 11px;
  border-radius: 980px;
  cursor: pointer;
  transition: all .18s;
}
.theme-switch button:hover { color: var(--text); }
.theme-switch button.on {
  background: var(--hover2);
  color: var(--text);
  font-weight: 500;
}

/* 用户信息 */
.user-chip {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 10px 5px 5px;
  border-radius: 980px;
  cursor: pointer;
  transition: background .18s;
}
.user-chip:hover { background: var(--hover); }
.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--grad-ava);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex: none;
}
.username { font-size: 14px; color: var(--text); }
.role-tag {
  font-size: 11px;
  padding: 2px 9px;
  border-radius: 980px;
  background: var(--hover);
  color: var(--text2);
  font-weight: 500;
}
.role-tag.admin {
  background: var(--primary-soft);
  color: var(--primary);
}

/* ===== Apple 式全屏菜单 ===== */
.mobile-menu {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--overlay);
  backdrop-filter: blur(30px);
  -webkit-backdrop-filter: blur(30px);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-8) var(--space-6);
  overflow-y: auto;
}
.mobile-menu-close {
  position: absolute;
  top: 18px;
  right: 20px;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: var(--bg);
  color: var(--text2);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all .18s;
}
.mobile-menu-close:hover { background: var(--hover); color: var(--text); }
.mobile-menu-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin: var(--space-4) 0 var(--space-8);
}
.mobile-menu-brand .mark {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: var(--grad-mark);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.mobile-menu-links {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  width: 100%;
  max-width: 480px;
}
.mobile-menu-link {
  font-size: 22px;
  font-weight: 500;
  color: var(--text2);
  font-family: inherit;
  padding: var(--space-3) var(--space-6);
  border: none;
  background: transparent;
  border-radius: 14px;
  cursor: pointer;
  transition: all .15s;
  width: 100%;
  text-align: center;
}
.mobile-menu-link:hover { background: var(--hover); color: var(--text); }
.mobile-menu-link.active {
  color: var(--text);
  font-weight: 600;
  background: var(--hover2);
}
.mobile-menu-user {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text2);
  font-size: 14px;
  padding: var(--space-6) 0 var(--space-2);
}

.menu-fade-enter-active,
.menu-fade-leave-active { transition: opacity .22s ease; }
.menu-fade-enter-from,
.menu-fade-leave-to { opacity: 0; }

/* ===== 内容区域 ===== */
.main-container {
  flex: 1;
  padding-top: 56px; /* 避开固定顶栏 */
  overflow: hidden;
  display: flex;
}
.content {
  flex: 1;
  overflow-y: auto;
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  padding: var(--space-7) var(--space-6);
}
/* Chat 页全宽全高（DeepSeek 布局） */
.content--flush {
  max-width: none;
  padding: 0;
}

/* ===== 响应式 ===== */
/* <1100px：隐藏居中导航，改汉堡全屏菜单 */
@media (max-width: 1100px) {
  .nav-links { display: none; }
  .hamburger { display: flex; }
}
/* <1280px：压缩右侧控件（隐藏文字，只留图标）避免与导航重叠 */
@media (max-width: 1279px) {
  .username,
  .role-tag { display: none; }
  .theme-switch button span { display: none; }
  .theme-switch button { padding: 6px 10px; }
}
@media (max-width: 760px) {
  .content { padding: var(--space-6) var(--space-4); }
  .content--flush { padding: 0; }
}
</style>
