<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, genFileId } from 'element-plus'
import api from '../api.js'

const PAGE_SIZE = 20

const uploadRef = ref(null)
const selectedFile = ref(null)
const category = ref('')
const uploading = ref(false)

const list = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

const categoryMap = { plan: '训练计划', diet: '营养资料', other: '其他' }
const statusMap = { READY: '就绪', FAILED: '失败', PROCESSING: '处理中' }

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function statusTagType(status) {
  if (status === 'READY') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status === 'PROCESSING') return 'warning'
  return 'info'
}

async function fetchList() {
  loading.value = true
  try {
    const data = await api.get('/documents', {
      params: { page: page.value, size: PAGE_SIZE }
    })
    total.value = data.total || 0
    list.value = data.list || []
    // 删空最后一页最后一条后回退一页重新加载
    if (!list.value.length && page.value > 1 && total.value > 0) {
      page.value -= 1
      await fetchList()
    }
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    loading.value = false
  }
}

function handlePageChange(next) {
  if (next === page.value) return
  page.value = next
  fetchList()
}

function handleFileChange(uploadFile) {
  selectedFile.value = uploadFile.raw || null
}

// 手动模式；超过 1 个文件时用新选择的文件替换旧的
function handleFileExceed(files) {
  uploadRef.value.clearFiles()
  const file = files[0]
  file.uid = genFileId()
  uploadRef.value.handleStart(file)
}

function handleFileRemove() {
  selectedFile.value = null
}

async function upload() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', selectedFile.value)
    if (category.value) {
      fd.append('category', category.value)
    }
    const data = await api.post('/documents', fd)
    if (data && data.dedup) {
      ElMessage.success('该文件已存在，秒传成功')
    } else {
      ElMessage.success('上传成功')
    }
    selectedFile.value = null
    if (uploadRef.value) {
      uploadRef.value.clearFiles()
    }
    page.value = 1
    await fetchList()
  } catch (e) {
    // 错误信息已由拦截器统一 alert，不重复提示
  } finally {
    uploading.value = false
  }
}

async function retry(doc) {
  try {
    await api.post(`/documents/${doc.docId}/retry`)
    ElMessage.success('已重新提交处理')
    await fetchList()
  } catch (e) {
    // 错误信息已由拦截器统一 alert，不重复提示
  }
}

async function remove(doc) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${doc.filename}」吗？删除后不可恢复。`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      }
    )
  } catch (e) {
    return // 用户取消
  }
  try {
    await api.delete(`/documents/${doc.docId}`)
    ElMessage.success('删除成功')
    await fetchList()
  } catch (e) {
    // 错误信息已由拦截器统一 alert，不重复提示
  }
}

onMounted(fetchList)
</script>

<template>
  <div class="page">
    <el-card class="doc-card">
      <h2>资料管理</h2>
      <p class="hint" style="margin-bottom: 20px">
        上传训练计划、饮食与营养资料等文档，处理后即可作为知识库问答的依据
      </p>

      <div class="upload-bar">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :on-exceed="handleFileExceed"
          :disabled="uploading"
        >
          <el-button :disabled="uploading">选择文件</el-button>
        </el-upload>
        <el-select
          v-model="category"
          placeholder="分类（可选）"
          clearable
          style="width: 150px"
          :disabled="uploading"
        >
          <el-option label="训练计划" value="plan" />
          <el-option label="营养资料" value="diet" />
          <el-option label="其他" value="other" />
        </el-select>
        <el-button
          type="primary"
          :disabled="!selectedFile"
          :loading="uploading"
          @click="upload"
        >
          {{ uploading ? '上传中…' : '上传' }}
        </el-button>
      </div>
      <p v-if="uploading" class="hint" style="margin-top: 8px">处理中…</p>

      <el-table
        v-loading="loading"
        :data="list"
        class="doc-table"
        empty-text="暂无资料，请先上传文件"
      >
        <el-table-column
          prop="filename"
          label="文件名"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column label="分类" width="110">
          <template #default="{ row }">
            {{ categoryMap[row.category] || '未分类' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">
              {{ statusMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分块数" width="90">
          <template #default="{ row }">
            {{ row.chunkCount != null ? row.chunkCount : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="200">
          <template #default="{ row }">
            <span v-if="row.status === 'FAILED' && row.failReason" class="fail-reason">
              {{ row.failReason }}
            </span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'FAILED'"
              link
              type="primary"
              size="small"
              @click="retry(row)"
            >
              重试
            </el-button>
            <el-button link type="danger" size="small" @click="remove(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > 0"
        class="doc-pager"
        background
        layout="prev, pager, next, total"
        :total="total"
        :page-size="PAGE_SIZE"
        :current-page="page"
        @current-change="handlePageChange"
      />
    </el-card>
  </div>
</template>

<style scoped>
.page {
  padding: 24px;
  display: flex;
  justify-content: center;
}

.doc-card {
  width: 100%;
  max-width: 960px;
}

h2 {
  margin-bottom: 8px;
  font-size: 18px;
  color: #1f2937;
}

.upload-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.doc-table {
  margin-top: 16px;
}

.fail-reason {
  color: #dc2626;
  font-size: 13px;
}

.doc-pager {
  margin-top: 16px;
  justify-content: center;
}
</style>