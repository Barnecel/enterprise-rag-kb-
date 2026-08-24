// -*- coding: utf-8 -*-
/**
 * Vue Router 路由配置
 * 管理应用的所有路由，包括登录、问答、管理员后台等
 */

import { createRouter, createWebHistory } from 'vue-router'

// 路由懒加载
const Login = () => import('../views/Login.vue')
const Register = () => import('../views/Register.vue')
const Home = () => import('../views/Home.vue')
const Chat = () => import('../views/Chat.vue')
const Document = () => import('../views/Document.vue')
const DocumentDetail = () => import('../views/DocumentDetail.vue')
const Profile = () => import('../views/Profile.vue')
const AdminDashboard = () => import('../views/AdminDashboard.vue')
const AdminUsers = () => import('../views/AdminUsers.vue')
const AdminDocuments = () => import('../views/AdminDocuments.vue')
const AdminCategories = () => import('../views/AdminCategories.vue')
const AdminLogs = () => import('../views/AdminLogs.vue')
const AdminFeedback = () => import('../views/AdminFeedback.vue')
const AdminModels = () => import('../views/AdminModels.vue')

// 路由配置
const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { title: '登录', requiresAuth: false }
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: { title: '注册', requiresAuth: false }
  },
  {
    path: '/',
    name: 'Home',
    component: Home,
    meta: { title: '首页', requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/chat'
      },
      {
        path: 'chat',
        name: 'Chat',
        component: Chat,
        meta: { title: '智能问答' }
      },
      {
        path: 'document',
        name: 'Document',
        component: Document,
        meta: { title: '知识库' }
      },
      {
        path: 'document/:id',
        name: 'DocumentDetail',
        component: DocumentDetail,
        meta: { title: '文档详情' }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: Profile,
        meta: { title: '个人中心' }
      },
      // 管理员子路由
      {
        path: 'admin/dashboard',
        name: 'AdminDashboard',
        component: AdminDashboard,
        meta: { title: '控制台', requiresAdmin: true }
      },
      {
        path: 'admin/users',
        name: 'AdminUsers',
        component: AdminUsers,
        meta: { title: '用户管理', requiresAdmin: true }
      },
      {
        path: 'admin/documents',
        name: 'AdminDocuments',
        component: AdminDocuments,
        meta: { title: '文档管理', requiresAdmin: true }
      },
      {
        path: 'admin/categories',
        name: 'AdminCategories',
        component: AdminCategories,
        meta: { title: '分类管理', requiresAdmin: true }
      },
      {
        path: 'admin/logs',
        name: 'AdminLogs',
        component: AdminLogs,
        meta: { title: '登录日志', requiresAdmin: true }
      },
      {
        path: 'admin/feedback',
        name: 'AdminFeedback',
        component: AdminFeedback,
        meta: { title: '反馈统计', requiresAdmin: true }
      },
      {
        path: 'admin/models',
        name: 'AdminModels',
        component: AdminModels,
        meta: { title: '模型接入', requiresAdmin: true }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login'
  }
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫 - 验证登录状态
router.beforeEach((to, from, next) => {
  // 设置页面标题
  document.title = to.meta.title ? `${to.meta.title} - 企业知识库` : '企业知识库'

  // 获取本地存储的token
  const token = localStorage.getItem('token')
  const userInfo = localStorage.getItem('userInfo')

  // 需要登录的页面
  if (to.meta.requiresAuth !== false) {
    if (!token || !userInfo) {
      next('/login')
      return
    }

    // 检查管理员权限
    if (to.meta.requiresAdmin) {
      try {
        const user = JSON.parse(userInfo)
        if (user.role !== 'admin') {
          next('/chat')
          return
        }
      } catch (e) {
        next('/login')
        return
      }
    }
  }

  // 已登录访问登录页则跳转到首页
  if (to.path === '/login' && token && userInfo) {
    next('/')
    return
  }

  next()
})

export default router