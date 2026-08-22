<template>
  <div class="profile-container">
    <div class="profile-card">
      <div class="profile-header">
        <div class="profile-avatar">{{ avatarText }}</div>
        <div class="profile-info">
          <h3>{{ userInfo.real_name || userInfo.username }}</h3>
          <p>{{ userInfo.email || '未设置邮箱' }}</p>
          <span class="role-tag" :class="userInfo.role">{{ userInfo.role === 'admin' ? '管理员' : '普通用户' }}</span>
        </div>
      </div>

      <el-form ref="profileFormRef" :model="profileForm" label-width="100px" class="profile-form">
        <el-form-item label="用户名">
          <el-input v-model="profileForm.username" disabled />
        </el-form-item>
        <el-form-item label="真实姓名">
          <el-input v-model="profileForm.real_name" placeholder="请输入真实姓名" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="profileForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="profileForm.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-input v-model="profileForm.tenant_name" disabled />
        </el-form-item>
        <el-form-item label="密级">
          <el-input :model-value="clearanceText(profileForm.clearance_level)" disabled />
        </el-form-item>
        <el-form-item label="注册时间">
          <el-input v-model="profileForm.created_at" disabled />
        </el-form-item>
        <el-form-item>
          <el-button class="btn-apple" :loading="saving" @click="handleSave">保存修改</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="profile-card">
      <h3 class="card-title">修改密码</h3>
      <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="100px" class="profile-form">
        <el-form-item label="旧密码" prop="old_password">
          <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="请输入旧密码" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="请输入新密码" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm_password">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password placeholder="请再次输入新密码" />
        </el-form-item>
        <el-form-item>
          <el-button class="btn-ghost" :loading="changing" @click="handleChangePassword">修改密码</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { userAPI, authAPI } from '../api'

const profileFormRef = ref(null)
const passwordFormRef = ref(null)
const saving = ref(false)
const changing = ref(false)

// 用户信息
// 密级定义（与后端 settings.CLEARANCE_LEVELS 一致）
const clearanceLevels = { 1: '公开', 2: '内部', 3: '机密', 4: '绝密' }
const clearanceText = (level) => clearanceLevels[level] || '公开'

const userInfo = ref({
  id: 0,
  username: '',
  real_name: '',
  email: '',
  phone: '',
  role: 'user',
  created_at: ''
})

const avatarText = computed(() => {
  const name = userInfo.value.real_name || userInfo.value.username
  return name ? name.slice(0, 1).toUpperCase() : 'U'
})

const profileForm = reactive({
  username: '',
  real_name: '',
  email: '',
  phone: '',
  tenant_name: '',
  clearance_level: 1,
  created_at: ''
})

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

// 密码表单验证
const validateConfirm = (rule, value, callback) => {
  if (value !== passwordForm.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const passwordRules = {
  old_password: [
    { required: true, message: '请输入旧密码', trigger: 'blur' }
  ],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少6位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' }
  ]
}

// 加载用户信息
const loadProfile = async () => {
  try {
    const res = await userAPI.getProfile()
    userInfo.value = res.data
    Object.assign(profileForm, res.data)
  } catch (error) {
    console.error('加载用户信息失败:', error)
  }
}

// 保存修改
const handleSave = async () => {
  saving.value = true
  try {
    await userAPI.updateProfile({
      real_name: profileForm.real_name,
      email: profileForm.email,
      phone: profileForm.phone
    })
    // 更新本地存储的用户信息
    userInfo.value.real_name = profileForm.real_name
    userInfo.value.email = profileForm.email
    userInfo.value.phone = profileForm.phone
    localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
    ElMessage.success('保存成功')
  } catch (error) {
    console.error('保存失败:', error)
  } finally {
    saving.value = false
  }
}

// 修改密码
const handleChangePassword = async () => {
  if (!passwordFormRef.value) return

  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return

    changing.value = true
    try {
      await authAPI.changePassword({
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password
      })
      ElMessage.success('密码修改成功')
      passwordFormRef.value.resetFields()
    } catch (error) {
      console.error('修改密码失败:', error)
    } finally {
      changing.value = false
    }
  })
}

onMounted(() => {
  loadProfile()
})
</script>

<style scoped>
.profile-container {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.profile-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  padding: var(--space-7);
}

.profile-header {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  padding-bottom: var(--space-6);
  border-bottom: 1px solid var(--border);
  margin-bottom: var(--space-7);
}

.profile-avatar {
  width: 76px;
  height: 76px;
  flex: none;
  border-radius: 50%;
  background: var(--grad-ava);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  font-weight: 700;
  box-shadow: 0 6px 20px rgba(0, 113, 227, .25);
}

.profile-info h3 {
  margin: 0 0 var(--space-1) 0;
  font-size: var(--text-title);
  font-weight: var(--text-title-w);
  letter-spacing: -.01em;
  color: var(--text);
}
.profile-info p {
  margin: 0 0 var(--space-3) 0;
  color: var(--text3);
  font-size: 14px;
}
.role-tag {
  font-size: 11.5px;
  padding: var(--space-1) var(--space-3);
  border-radius: 980px;
  background: var(--hover);
  color: var(--text2);
  font-weight: 500;
}
.role-tag.admin {
  background: var(--primary-soft);
  color: var(--primary);
}

.card-title {
  margin: 0 0 var(--space-6) 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text);
}

.profile-form {
  max-width: 500px;
}
.profile-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  background: var(--bg);
  box-shadow: 0 0 0 1px var(--border) inset;
  transition: box-shadow .2s;
}
.profile-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1.5px var(--primary) inset, 0 0 0 4px var(--primary-soft);
}
.profile-form :deep(.el-input__inner) { color: var(--text); }
.profile-form :deep(.el-form-item__label) { color: var(--text2); }

.btn-apple {
  border: none;
  background: var(--grad-btn);
  color: #fff;
  font-weight: 600;
  height: 38px;
  padding: 0 var(--space-5);
  border-radius: 980px;
}
.btn-apple:hover { filter: brightness(1.06); color: #fff; }
.btn-apple:active { transform: scale(.97); }
.btn-ghost {
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text2);
  font-weight: 500;
  height: 38px;
  border-radius: 980px;
}
.btn-ghost:hover { border-color: var(--primary); color: var(--primary); background: var(--card); }
</style>
