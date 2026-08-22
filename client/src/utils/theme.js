// -*- coding: utf-8 -*-
/**
 * 主题切换：auto（跟随时间）/ light / dark
 *   auto 规则：19:00 - 次日 7:00 深色，其余浅色
 *   偏好存 localStorage('kb_theme')，每 30s 复查一次时间
 */

const STORAGE_KEY = 'kb_theme'

let override = 'auto'
let timer = null

function autoTheme() {
  const h = new Date().getHours()
  return (h >= 19 || h < 7) ? 'dark' : 'light'
}

/** 应用当前主题到 <html>（data-theme 供本主题，.dark 供 Element Plus 深色） */
export function applyTheme() {
  const mode = override === 'auto' ? autoTheme() : override
  const el = document.documentElement
  el.setAttribute('data-theme', mode)
  el.classList.toggle('dark', mode === 'dark')
  return mode
}

/** 当前偏好：'auto' | 'light' | 'dark' */
export function getThemePreference() {
  return override
}

/** 设置偏好并立即生效 */
export function setThemePreference(mode) {
  if (!['auto', 'light', 'dark'].includes(mode)) mode = 'auto'
  override = mode
  try { localStorage.setItem(STORAGE_KEY, mode) } catch (e) { /* ignore */ }
  applyTheme()
}

/** 应用启动时初始化（index.html 内联脚本已做过一次，此处幂等） */
export function initTheme() {
  try { override = localStorage.getItem(STORAGE_KEY) || 'auto' } catch (e) { /* ignore */ }
  applyTheme()
  if (timer) clearInterval(timer)
  timer = setInterval(applyTheme, 30000)
}
