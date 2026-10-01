import { ref, computed, onMounted, onUnmounted } from 'vue';
import { settingsApi } from '@/api/settings';
import { ElMessage, ElMessageBox } from 'element-plus';
import { testTiandituServerKey } from '@/utils/mapKeyTester';
export function useMapSettings() {
  const mapForm = ref({
    provider: 'tianditu',
    api_keys: [''] as string[]
  });
  type MapKeyTestState = {
    status: 'idle' | 'testing' | 'valid' | 'invalid';
    message: string;
  };
  const idleMapKeyTest = (): MapKeyTestState => ({ status: 'idle', message: '' });
  const mapKeyTests = ref<MapKeyTestState[]>([idleMapKeyTest()]);
  const testingAllMapKeys = ref(false);
  const savingMapSettings = ref(false);
  const syncMapKeyTests = () => {
    mapKeyTests.value = mapForm.value.api_keys.map((_, index) => mapKeyTests.value[index] || idleMapKeyTest());
  };
  const resetMapKeyTest = (index: number) => {
    mapKeyTests.value[index] = idleMapKeyTest();
  };
  const resetMapKeyTests = () => {
    mapKeyTests.value = mapForm.value.api_keys.map(() => idleMapKeyTest());
  };
  const addMapKey = () => {
    mapForm.value.api_keys.push('');
    mapKeyTests.value.push(idleMapKeyTest());
  };
  const removeMapKey = (index: number) => {
    mapForm.value.api_keys.splice(index, 1);
    mapKeyTests.value.splice(index, 1);
  };
  const countries = ref<any[]>([]);
  const downloadedCountries = ref<any[]>([]);
  const selectedCountry = ref('');
  const downloadPhase = ref<'idle' | 'downloading' | 'done' | 'failed' | 'timeout'>('idle');
  const downloadProgress = ref(0);
  const downloadingCountryName = ref('');
  const downloading = computed(() => downloadPhase.value === 'downloading');
  const downloadProgressStatus = computed(() => {
    if (downloadPhase.value === 'done')
      return 'success';
    if (downloadPhase.value === 'failed')
      return 'exception';
    return '';
  });
  const downloadStatusText = computed(() => {
    const name = downloadingCountryName.value;
    switch (downloadPhase.value) {
      case 'downloading': return `正在下载${name ? ` ${name}` : ''} 离线数据...`;
      case 'done': return `${name || ''} 数据下载完成`;
      case 'failed': return '下载失败';
      case 'timeout': return '下载仍在后台进行';
      default: return '';
    }
  });
  const downloadHint = computed(() => {
    switch (downloadPhase.value) {
      case 'downloading':
        return downloadProgress.value >= 85
          ? '数据较多，正在后台处理...'
          : '正在从数据源获取城市坐标，完成后即可用于离线解析';
      case 'done': return '可在「任务管理」中重新执行元数据提取任务以应用新数据';
      case 'failed': return '请检查网络后重试，或使用「上传自定义数据」导入';
      case 'timeout': return '后台仍在下载，可稍后点击「刷新」查看';
      default: return '';
    }
  });
  const downloadingFiles = ref(new Set<string>());
  const refreshingMapData = ref(false);
  const loadMapDataInfo = async () => {
    try {
      const [cData, dData] = await Promise.all([
        settingsApi.getMapCountries(),
        settingsApi.getDownloadedMapData()
      ]);
      countries.value = cData;
      downloadedCountries.value = dData;
    }
    catch (e) {
      console.error('Failed to load map data info', e);
    }
  };
  const handleRefreshMapData = async () => {
    refreshingMapData.value = true;
    await loadMapDataInfo();
    refreshingMapData.value = false;
    ElMessage.success('数据已刷新');
  };
  // 下载进度模拟与完成检测定时器
  let mapProgressTimer: number | null = null;
  let mapPollTimer: number | null = null;
  let mapDeadlineTimer: number | null = null;
  let mapFinishTimer: number | null = null;
  const clearMapTimers = () => {
    if (mapProgressTimer) {
      clearInterval(mapProgressTimer);
      mapProgressTimer = null;
    }
    if (mapPollTimer) {
      clearInterval(mapPollTimer);
      mapPollTimer = null;
    }
    if (mapDeadlineTimer) {
      clearTimeout(mapDeadlineTimer);
      mapDeadlineTimer = null;
    }
  };
  const resetDownload = () => {
    if (mapFinishTimer) {
      clearTimeout(mapFinishTimer);
      mapFinishTimer = null;
    }
    downloadPhase.value = 'idle';
    downloadProgress.value = 0;
    downloadingCountryName.value = '';
  };
  // 模拟进度：渐进收敛到 90%，越接近越慢，留余量等真实完成检测收尾
  const startProgressSim = () => {
    downloadProgress.value = 0;
    mapProgressTimer = window.setInterval(() => {
      const remaining = 90 - downloadProgress.value;
      if (remaining > 0.5) {
        downloadProgress.value = Math.min(90, downloadProgress.value + remaining * 0.12);
      }
    }, 500);
  };
  // 真实完成检测：轮询已下载列表，目标国家 CSV 一出现即收尾
  const startCompletionPoll = (code: string) => {
    mapPollTimer = window.setInterval(async () => {
      await loadMapDataInfo();
      if (downloadedCountries.value.some(it => it.code === code)) {
        finishDownload('done');
      }
    }, 2500);
    // 3 分钟超时兜底：后台仍可能在跑，但不让用户无限等
    mapDeadlineTimer = window.setTimeout(() => {
      if (downloadPhase.value === 'downloading') {
        finishDownload('timeout');
      }
    }, 180000);
  };
  const finishDownload = (phase: 'done' | 'timeout') => {
    clearMapTimers();
    downloadPhase.value = phase;
    const name = downloadingCountryName.value;
    if (phase === 'done') {
      downloadProgress.value = 100;
      ElMessage.success(`${name} 数据下载完成`);
      mapFinishTimer = window.setTimeout(resetDownload, 1800);
    }
    else {
      ElMessage.warning(`${name} 下载耗时较长，请稍后刷新查看`);
      mapFinishTimer = window.setTimeout(resetDownload, 2800);
    }
  };
  const finishFailed = () => {
    clearMapTimers();
    downloadPhase.value = 'failed';
    ElMessage.error('下载请求失败');
    mapFinishTimer = window.setTimeout(resetDownload, 2200);
  };
  const downloadCountry = async () => {
    if (!selectedCountry.value)
      return;
    const code = selectedCountry.value;
    const country = countries.value.find(c => c.code === code);
    const name = country?.name || code;
    // 进入下载态，立即给用户反馈
    clearMapTimers();
    downloadPhase.value = 'downloading';
    downloadingCountryName.value = name;
    downloadProgress.value = 0;
    selectedCountry.value = '';
    try {
      await settingsApi.downloadMapData(code);
      // 请求成功发出，启动模拟进度 + 完成轮询
      startProgressSim();
      startCompletionPoll(code);
    }
    catch (e) {
      finishFailed();
    }
  };
  const handleUploadMapData = async (options: any) => {
    const { file } = options;
    try {
      await settingsApi.uploadMapData(file);
      ElMessage.success('上传成功');
      await loadMapDataInfo();
    }
    catch (e: any) {
      const msg = e.response?.data?.detail || '上传失败';
      ElMessage.error(msg);
    }
  };
  const downloadFile = async (filename: string) => {
    if (downloadingFiles.value.has(filename))
      return;
    downloadingFiles.value.add(filename);
    ElMessage.info(`开始下载文件: ${filename}`);
    try {
      const blob = await settingsApi.downloadMapFile(filename);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      window.URL.revokeObjectURL(url);
      ElMessage.success(`文件 ${filename} 下载完成`);
    }
    catch (e) {
      ElMessage.error(`文件 ${filename} 下载失败`);
    }
    finally {
      downloadingFiles.value.delete(filename);
    }
  };
  const deleteFile = async (filename: string) => {
    try {
      await ElMessageBox.confirm(`确定要删除已下载的数据文件 "${filename}" 吗？`, '删除确认', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await settingsApi.deleteMapData(filename);
      ElMessage.success('删除成功');
      await loadMapDataInfo();
    }
    catch (e) {
      if (e !== 'cancel') {
        ElMessage.error('删除失败');
      }
    }
  };
  const testMapKey = async (index: number): Promise<boolean> => {
    const apiKey = mapForm.value.api_keys[index]?.trim();
    if (!apiKey) {
      mapKeyTests.value[index] = { status: 'invalid', message: '请先输入 API Key' };
      return false;
    }
    mapKeyTests.value[index] = { status: 'testing', message: '正在连接天地图…' };
    try {
      if (mapForm.value.provider !== 'tianditu') {
        mapKeyTests.value[index] = { status: 'invalid', message: '暂不支持测试该地图提供商' };
        return false;
      }
      const result = await testTiandituServerKey(apiKey);
      if (result?.valid) {
        mapKeyTests.value[index] = { status: 'valid', message: '连接成功，Key 可用' };
        return true;
      }
      mapKeyTests.value[index] = { status: 'invalid', message: result?.reason || 'Key 不可用，请检查配置' };
      return false;
    }
    catch (error: any) {
      mapKeyTests.value[index] = {
        status: 'invalid',
        message: error?.msg || error?.message || '测试失败，请稍后重试'
      };
      return false;
    }
  };
  const testAllMapKeys = async (): Promise<boolean> => {
    syncMapKeyTests();
    testingAllMapKeys.value = true;
    try {
      const results = await Promise.all(mapForm.value.api_keys.map((_, index) => testMapKey(index)));
      const allValid = results.length > 0 && results.every(Boolean);
      if (allValid)
        ElMessage.success('所有地图 API Key 均可用');
      return allValid;
    }
    finally {
      testingAllMapKeys.value = false;
    }
  };
  const saveMapSettings = async () => {
    const normalizedKeys = [...new Set(mapForm.value.api_keys.map(key => key.trim()).filter(Boolean))];
    if (!normalizedKeys.length) {
      mapKeyTests.value[0] = { status: 'invalid', message: '至少需要填写一个 API Key' };
      ElMessage.warning('请先填写地图 API Key');
      return;
    }
    mapForm.value.api_keys = normalizedKeys;
    resetMapKeyTests();
    savingMapSettings.value = true;
    try {
      const allValid = await testAllMapKeys();
      if (!allValid) {
        ElMessage.error('存在不可用的地图 API Key，请修正后再保存');
        return;
      }
      await settingsApi.updateSettings({ map: mapForm.value });
      ElMessage.success('地图配置已保存');
    }
    catch (e) {
      ElMessage.error('保存失败');
    }
    finally {
      savingMapSettings.value = false;
    }
  };
  onMounted(loadMapDataInfo);
  onUnmounted(() => { clearMapTimers(); if (mapFinishTimer)
    clearTimeout(mapFinishTimer); });
  return { mapForm, idleMapKeyTest, mapKeyTests, testingAllMapKeys, savingMapSettings, syncMapKeyTests, resetMapKeyTest, resetMapKeyTests, addMapKey, removeMapKey, countries, downloadedCountries, selectedCountry, downloadPhase, downloadProgress, downloadingCountryName, downloading, downloadProgressStatus, downloadStatusText, downloadHint, downloadingFiles, refreshingMapData, loadMapDataInfo, handleRefreshMapData, clearMapTimers, resetDownload, startProgressSim, startCompletionPoll, finishDownload, finishFailed, downloadCountry, handleUploadMapData, downloadFile, deleteFile, testMapKey, testAllMapKeys, saveMapSettings };
}
