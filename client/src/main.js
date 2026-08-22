// -*- coding: utf-8 -*-
/**
 * Vue应用入口文件
 * 配置路由、Element Plus等插件
 */

import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import App from './App.vue'
import router from './router'
import './styles/theme.css'
import { initTheme } from './utils/theme'

// 应用启动即初始化主题（auto/light/dark，auto 跟随时间）
initTheme()

// 创建Vue应用
const app = createApp(App)

// 使用Element Plus组件库（中文）
app.use(ElementPlus, { locale: zhCn })

// 使用路由
app.use(router)

// 挂载到#app元素
app.mount('#app')