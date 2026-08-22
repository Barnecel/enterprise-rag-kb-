<template>
  <div class="login-page">
    <div class="glow g1"></div>
    <div class="glow g2"></div>

    <div class="login-card">
      <div class="mark">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L19.7 10l-5.8 1.9L12 17.7l-1.9-5.8L4.3 10l5.8-1.2z"/><path d="M19 15l.7 2.2L22 18l-2.3.8L19 21l-.7-2.2L16 18l2.3-.8z"/></svg>
      </div>
      <h1>企业知识库</h1>
      <div class="sub">创建你的账号</div>

      <el-form ref="registerFormRef" :model="registerForm" :rules="rules" size="large">
        <el-form-item prop="username">
          <el-input v-model="registerForm.username" placeholder="用户名(3-20位)" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="registerForm.password" type="password" placeholder="密码(至少6位)" :prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item prop="real_name">
          <el-input v-model="registerForm.real_name" placeholder="真实姓名" :prefix-icon="UserFilled" />
        </el-form-item>
        <el-form-item prop="email">
          <el-input v-model="registerForm.email" placeholder="邮箱" :prefix-icon="Message" />
        </el-form-item>
        <el-form-item prop="phone">
          <el-input v-model="registerForm.phone" placeholder="手机号" :prefix-icon="Phone" />
        </el-form-item>
        <el-form-item>
          <el-button class="btn-apple register-btn" :loading="loading" @click="handleRegister">注册</el-button>
        </el-form-item>
      </el-form>

      <div class="footer">
        已有账号？<router-link to="/login">立即登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, UserFilled, Message, Phone } from '@element-plus/icons-vue'
import { authAPI } from '../api'

const router = useRouter()
const registerFormRef = ref(null)
const loading = ref(false)

const registerForm = reactive({
  username: '',
  password: '',
  real_name: '',
  email: '',
  phone: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度3-20位', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ],
  real_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入有效的邮箱', trigger: 'blur' }
  ]
}

const handleRegister = async () => {
  if (!registerFormRef.value) return

  await registerFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      await authAPI.register(registerForm)
      ElMessage.success('注册成功，请登录')
      router.push('/login')
    } catch (error) {
      console.error('注册失败:', error)
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 96px var(--space-5) var(--space-8);
  background: var(--bg);
  transition: background .35s;
}

.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: .55;
  pointer-events: none;
}
.glow.g1 {
  width: 560px; height: 560px;
  background: var(--glow1);
  top: -160px; left: 50%;
  transform: translateX(-50%);
}
.glow.g2 {
  width: 420px; height: 420px;
  background: var(--glow2);
  bottom: -180px; left: -80px;
}

.login-card {
  position: relative;
  width: 100%;
  max-width: 400px;
  background: var(--overlay);
  backdrop-filter: saturate(180%) blur(24px);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  border: 1px solid var(--border);
  border-radius: 22px;
  box-shadow: var(--shadow);
  padding: var(--space-8) 40px var(--space-7);
  text-align: center;
}

.mark {
  width: 64px;
  height: 64px;
  margin: 0 auto var(--space-5);
  border-radius: 16px;
  background: var(--grad-mark);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 8px 24px rgba(0, 113, 227, .35);
}

h1 {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--text);
}
.sub {
  font-size: 13px;
  color: var(--text3);
  margin: var(--space-2) 0 var(--space-7);
}

.login-card :deep(.el-input__wrapper) {
  border-radius: 12px;
  background: var(--input-bg);
  box-shadow: 0 0 0 1px var(--border) inset;
  padding: var(--space-1) var(--space-4);
}
.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1.5px var(--primary) inset, 0 0 0 4px var(--primary-soft);
}
.login-card :deep(.el-input__inner) {
  color: var(--text);
}

.register-btn {
  width: 100%;
  height: 46px;
  font-size: 16px;
}

.footer {
  font-size: 13px;
  color: var(--text3);
  margin-top: var(--space-4);
}
.footer a { margin-left: 5px; }
</style>
