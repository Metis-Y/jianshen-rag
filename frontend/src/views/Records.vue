<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api.js'

// ---------- 日期工具 ----------
function fmtDate(d) {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}
function todayStr() {
  return fmtDate(new Date())
}
function daysAgoStr(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return fmtDate(d)
}

// 最近记录查询区间：近 30 天
const LIST_FROM = daysAgoStr(29)
const LIST_TO = todayStr()

// 日期选择器不允许未来
function disableFuture(d) {
  return d.getTime() > Date.now()
}

const activeTab = ref('workout')

// ---------- 训练 ----------
const workoutDate = ref(todayStr())
const workoutNote = ref('')
const exerciseRows = ref([{ name: '', weight: null, sets: null, reps: null }])
const workoutSubmitting = ref(false)
const workoutLoading = ref(false)
const lastVolume = ref(null)
const workoutRecords = ref([])
const workoutTotalVolume = ref(0)

function addExerciseRow() {
  exerciseRows.value.push({ name: '', weight: null, sets: null, reps: null })
}
function removeExerciseRow(index) {
  if (exerciseRows.value.length <= 1) return
  exerciseRows.value.splice(index, 1)
}

async function fetchWorkouts() {
  workoutLoading.value = true
  try {
    const data = await api.get('/workouts', {
      params: { from: LIST_FROM, to: LIST_TO }
    })
    workoutRecords.value = (data && data.records) || []
    workoutTotalVolume.value = (data && data.totalVolume) || 0
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    workoutLoading.value = false
  }
}

async function submitWorkout() {
  if (!workoutDate.value) {
    ElMessage.warning('请选择训练日期')
    return
  }
  // 快速模式：只填动作名也可提交；空动作行直接忽略
  const exercises = exerciseRows.value
    .filter((r) => r.name && r.name.trim())
    .map((r) => {
      const ex = { name: r.name.trim() }
      if (r.weight != null) ex.weight = r.weight
      if (r.sets != null) ex.sets = r.sets
      if (r.reps != null) ex.reps = r.reps
      return ex
    })
  if (!exercises.length) {
    ElMessage.warning('请至少填写一个动作名')
    return
  }
  workoutSubmitting.value = true
  try {
    const data = await api.post('/workouts', {
      date: workoutDate.value,
      exercises,
      note: workoutNote.value.trim() || undefined
    })
    lastVolume.value = data && data.volume != null ? data.volume : null
    ElMessage.success('训练已记录')
    exerciseRows.value = [{ name: '', weight: null, sets: null, reps: null }]
    workoutNote.value = ''
    await fetchWorkouts()
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    workoutSubmitting.value = false
  }
}

// ---------- 体征 ----------
const metricDate = ref(todayStr())
const weight = ref(null)
const metricSubmitting = ref(false)
const metricLoading = ref(false)
const metricsData = ref(null) // { latest, delta, series }

function fmtDelta(delta) {
  if (delta == null) return '—'
  return (delta > 0 ? '+' : '') + delta.toFixed(1)
}

async function fetchMetrics() {
  metricLoading.value = true
  try {
    metricsData.value = await api.get('/metrics', {
      params: { from: LIST_FROM, to: LIST_TO }
    })
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    metricLoading.value = false
  }
}

async function submitMetric() {
  if (!metricDate.value) {
    ElMessage.warning('请选择日期')
    return
  }
  if (weight.value == null) {
    ElMessage.warning('请填写体重')
    return
  }
  metricSubmitting.value = true
  try {
    await api.post('/metrics', {
      date: metricDate.value,
      weight: weight.value
    })
    ElMessage.success('体征已记录')
    weight.value = null
    await fetchMetrics()
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    metricSubmitting.value = false
  }
}

// ---------- 饮食 ----------
const dietDate = ref(todayStr())
const dietContent = ref('')
const avoidTags = ref([])
const avoidInput = ref('')
const dietSubmitting = ref(false)
const dietLoading = ref(false)
const dietRecords = ref([])

function addAvoidTag() {
  const tag = avoidInput.value.trim()
  if (!tag) return
  if (!avoidTags.value.includes(tag)) {
    avoidTags.value.push(tag)
  }
  avoidInput.value = ''
}
function removeAvoidTag(tag) {
  avoidTags.value = avoidTags.value.filter((t) => t !== tag)
}

async function fetchDiets() {
  dietLoading.value = true
  try {
    const data = await api.get('/diets', {
      params: { from: LIST_FROM, to: LIST_TO }
    })
    dietRecords.value = (data && data.records) || []
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    dietLoading.value = false
  }
}

async function submitDiet() {
  if (!dietDate.value) {
    ElMessage.warning('请选择日期')
    return
  }
  if (!dietContent.value.trim()) {
    ElMessage.warning('请填写饮食内容')
    return
  }
  dietSubmitting.value = true
  try {
    const avoid = avoidTags.value.map((t) => t.trim()).filter(Boolean)
    await api.post('/diets', {
      date: dietDate.value,
      content: dietContent.value.trim(),
      avoid
    })
    ElMessage.success('饮食已记录')
    dietContent.value = ''
    avoidTags.value = []
    await fetchDiets()
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    dietSubmitting.value = false
  }
}

// ---------- 偏好 ----------
const GOAL_OPTIONS = [
  { label: '减脂', value: '减脂' },
  { label: '增肌', value: '增肌' },
  { label: '维持', value: '维持' }
]
const goal = ref(null)
const allergyTags = ref([])
const allergyInput = ref('')
const preferenceLoading = ref(false)
const preferenceSaving = ref(false)

function addAllergyTag() {
  const tag = allergyInput.value.trim()
  if (!tag) return
  if (!allergyTags.value.includes(tag)) {
    allergyTags.value.push(tag)
  }
  allergyInput.value = ''
}
function removeAllergyTag(tag) {
  allergyTags.value = allergyTags.value.filter((t) => t !== tag)
}

async function fetchPreference() {
  preferenceLoading.value = true
  try {
    const data = await api.get('/preference')
    goal.value = (data && data.goal) || null
    allergyTags.value = (data && Array.isArray(data.allergies) && data.allergies) || []
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    preferenceLoading.value = false
  }
}

async function savePreference() {
  preferenceSaving.value = true
  try {
    // 整体覆盖：清空场景下 goal=null、allergies=[] 原样提交
    await api.put('/preference', {
      goal: goal.value || null,
      allergies: allergyTags.value.map((t) => t.trim()).filter(Boolean)
    })
    ElMessage.success('偏好已保存')
    await fetchPreference()
  } catch (e) {
    // 错误信息已由拦截器统一 alert
  } finally {
    preferenceSaving.value = false
  }
}

// ---------- 初始化 ----------
onMounted(() => {
  fetchWorkouts()
  fetchMetrics()
  fetchDiets()
  fetchPreference()
})

// 体征 series 展示最近 7 条（最近的在前）
const recentSeries = computed(() => {
  const series =
    metricsData.value && Array.isArray(metricsData.value.series)
      ? metricsData.value.series
      : []
  return series.slice(-7).reverse()
})
</script>

<template>
  <div class="page">
    <el-card class="record-card">
      <h2>记录</h2>
      <p class="hint" style="margin-bottom: 20px">
        记录每日训练、体征与饮食，管理长期训练偏好
      </p>

      <el-tabs v-model="activeTab">
        <!-- ============ 训练 ============ -->
        <el-tab-pane label="训练" name="workout">
          <el-form label-width="70px" @submit.prevent>
            <el-form-item label="日期" required>
              <el-date-picker
                v-model="workoutDate"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                :clearable="false"
                :disabled-date="disableFuture"
                style="width: 160px"
              />
            </el-form-item>

            <el-form-item label="动作">
              <div class="exercise-list">
                <div
                  v-for="(row, index) in exerciseRows"
                  :key="index"
                  class="exercise-row"
                >
                  <el-input
                    v-model="row.name"
                    placeholder="动作名（如：深蹲）"
                    style="width: 220px"
                  />
                  <el-input-number
                    v-model="row.weight"
                    :min="0"
                    :step="0.5"
                    placeholder="重量"
                    controls-position="right"
                    style="width: 120px"
                  />
                  <span class="unit">kg</span>
                  <el-input-number
                    v-model="row.sets"
                    :min="0"
                    :step="1"
                    :precision="0"
                    placeholder="组数"
                    controls-position="right"
                    style="width: 110px"
                  />
                  <span class="unit">组</span>
                  <el-input-number
                    v-model="row.reps"
                    :min="0"
                    :step="1"
                    :precision="0"
                    placeholder="次数"
                    controls-position="right"
                    style="width: 110px"
                  />
                  <span class="unit">次</span>
                  <el-button
                    type="danger"
                    plain
                    size="small"
                    :disabled="exerciseRows.length <= 1"
                    @click="removeExerciseRow(index)"
                  >
                    删除
                  </el-button>
                </div>
                <el-button size="small" @click="addExerciseRow">
                  + 添加动作
                </el-button>
                <p class="hint">
                  快速记录：只填动作名即可提交，重量/组数/次数可留空
                </p>
              </div>
            </el-form-item>

            <el-form-item label="备注">
              <el-input
                v-model="workoutNote"
                type="textarea"
                :rows="2"
                maxlength="200"
                show-word-limit
                placeholder="状态、感受等（可选）"
              />
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="workoutSubmitting"
                @click="submitWorkout"
              >
                {{ workoutSubmitting ? '提交中…' : '记录训练' }}
              </el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="lastVolume != null"
            type="success"
            :closable="false"
            class="volume-bar"
          >
            本次训练已记录，容量：
            <strong>{{ lastVolume }} kg</strong>
          </el-alert>

          <div v-loading="workoutLoading" class="sub-list">
            <div class="sub-title">
              最近训练记录
              <span v-if="workoutRecords.length" class="hint">
                （近 30 天总容量 {{ workoutTotalVolume }} kg）
              </span>
            </div>
            <el-table :data="workoutRecords" empty-text="暂无训练记录">
              <el-table-column prop="date" label="日期" width="120" />
              <el-table-column label="容量" width="130">
                <template #default="{ row }">
                  {{ row.volume != null ? row.volume + ' kg' : '—' }}
                </template>
              </el-table-column>
              <el-table-column label="动作数" width="90">
                <template #default="{ row }">
                  {{ row.exercises ? row.exercises.length : 0 }}
                </template>
              </el-table-column>
              <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.note || '—' }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- ============ 体征 ============ -->
        <el-tab-pane label="体征" name="metric">
          <el-form label-width="70px" @submit.prevent>
            <el-form-item label="日期" required>
              <el-date-picker
                v-model="metricDate"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                :clearable="false"
                :disabled-date="disableFuture"
                style="width: 160px"
              />
            </el-form-item>
            <el-form-item label="体重" required>
              <el-input-number
                v-model="weight"
                :min="0"
                :step="0.1"
                :precision="2"
                placeholder="如 72.30"
                controls-position="right"
                style="width: 180px"
              />
              <span class="unit">kg</span>
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="metricSubmitting"
                @click="submitMetric"
              >
                {{ metricSubmitting ? '提交中…' : '记录体征' }}
              </el-button>
            </el-form-item>
          </el-form>

          <div v-loading="metricLoading" class="sub-list">
            <div class="sub-title">最近体征记录</div>
            <template v-if="metricsData">
              <el-alert
                v-if="metricsData.latest"
                :closable="false"
                class="volume-bar"
              >
                最新体重：<strong>{{ metricsData.latest.weight }} kg</strong>
                （{{ metricsData.latest.date }}）·
                较上次变化：
                <strong>{{ fmtDelta(metricsData.delta) }} kg</strong>
              </el-alert>
              <el-table :data="recentSeries" empty-text="暂无体征记录">
                <el-table-column prop="date" label="日期" width="140" />
                <el-table-column label="体重" width="140">
                  <template #default="{ row }">
                    {{ row.weight != null ? row.weight + ' kg' : '—' }}
                  </template>
                </el-table-column>
              </el-table>
            </template>
            <p v-else class="hint">暂无体征记录</p>
          </div>
        </el-tab-pane>

        <!-- ============ 饮食 ============ -->
        <el-tab-pane label="饮食" name="diet">
          <el-form label-width="70px" @submit.prevent>
            <el-form-item label="日期" required>
              <el-date-picker
                v-model="dietDate"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                :clearable="false"
                :disabled-date="disableFuture"
                style="width: 160px"
              />
            </el-form-item>
            <el-form-item label="内容" required>
              <el-input
                v-model="dietContent"
                type="textarea"
                :rows="3"
                maxlength="500"
                show-word-limit
                placeholder="如：鸡胸肉 + 糙米 + 西兰花"
              />
            </el-form-item>
            <el-form-item label="本次忌口">
              <div class="tag-area">
                <el-input
                  v-model="avoidInput"
                  placeholder="输入忌口后回车（如：牛奶）"
                  style="width: 240px"
                  @keyup.enter.prevent="addAvoidTag"
                />
                <span
                  v-for="tag in avoidTags"
                  :key="tag"
                  class="avoid-tag"
                >
                  {{ tag }}
                  <span class="avoid-tag-close" @click="removeAvoidTag(tag)">×</span>
                </span>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="dietSubmitting"
                @click="submitDiet"
              >
                {{ dietSubmitting ? '提交中…' : '记录饮食' }}
              </el-button>
            </el-form-item>
          </el-form>

          <div v-loading="dietLoading" class="sub-list">
            <div class="sub-title">最近饮食记录</div>
            <el-table :data="dietRecords" empty-text="暂无饮食记录">
              <el-table-column prop="date" label="日期" width="120" />
              <el-table-column prop="content" label="内容" min-width="220" show-overflow-tooltip />
              <el-table-column label="忌口" min-width="160">
                <template #default="{ row }">
                  <span v-if="row.avoid && row.avoid.length">
                    {{ row.avoid.join('、') }}
                  </span>
                  <span v-else>—</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- ============ 偏好 ============ -->
        <el-tab-pane label="偏好" name="preference">
          <div v-loading="preferenceLoading" class="pref-body">
            <el-form label-width="90px" @submit.prevent>
              <el-form-item label="目标">
                <el-select
                  v-model="goal"
                  placeholder="请选择训练目标"
                  clearable
                  style="width: 200px"
                >
                  <el-option
                    v-for="opt in GOAL_OPTIONS"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="长期忌口">
                <div class="tag-area">
                  <el-input
                    v-model="allergyInput"
                    placeholder="输入忌口后回车（如：花生）"
                    style="width: 240px"
                    @keyup.enter.prevent="addAllergyTag"
                  />
                  <span
                    v-for="tag in allergyTags"
                    :key="tag"
                    class="avoid-tag"
                  >
                    {{ tag }}
                    <span class="avoid-tag-close" @click="removeAllergyTag(tag)">×</span>
                  </span>
                </div>
                <p class="hint">保存为整体覆盖：清空后保存即清除原有偏好</p>
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  :loading="preferenceSaving"
                  @click="savePreference"
                >
                  {{ preferenceSaving ? '保存中…' : '保存偏好' }}
                </el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.page {
  padding: 24px;
  display: flex;
  justify-content: center;
}

.record-card {
  width: 100%;
  max-width: 960px;
}

h2 {
  margin-bottom: 8px;
  font-size: 18px;
  color: #1f2937;
}

.hint {
  color: #6b7280;
  font-size: 12px;
}

.exercise-list {
  width: 100%;
}

.exercise-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.unit {
  color: #6b7280;
  font-size: 13px;
}

.volume-bar {
  margin: 4px 0 16px;
}

.tag-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
}

.avoid-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  color: #409eff;
  border-radius: 4px;
  font-size: 12px;
}

.avoid-tag-close {
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.avoid-tag-close:hover {
  color: #dc2626;
}

.sub-list {
  margin-top: 16px;
  min-height: 40px;
}

.sub-title {
  font-weight: 600;
  color: #1f2937;
  font-size: 14px;
  margin-bottom: 8px;
}

.sub-title .hint {
  font-weight: 400;
}

.pref-body {
  max-width: 560px;
}
</style>