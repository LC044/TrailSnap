const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed } = require('vue')
const root = path.resolve(__dirname, '../../src')
const transpile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b }); return {promise,resolve,reject} }

function cacheHarness() {
  const module = { exports: {} }
  let now = 100
  vm.runInNewContext(transpile(fs.readFileSync(path.join(root,'utils/locationMetadataCache.ts'),'utf8')), {
    module, exports: module.exports, require: () => ({ref}), Date: {now: () => now},
  })
  return {...module.exports, advance: ms => {now += ms}}
}

test('metadata shares in-flight requests, expires, and isolates account keys', async () => {
  const cache = cacheHarness(), pending = deferred()
  let calls = 0
  const load = () => {calls++; return pending.promise}
  const first = cache.cachedLocationMetadata('server:user:years',load)
  const second = cache.cachedLocationMetadata('server:user:years',load)
  assert.equal(first,second)
  pending.resolve([2024]); await first
  await cache.cachedLocationMetadata('server:user:years',load)
  assert.equal(calls,1)
  await cache.cachedLocationMetadata('server:other:years',load)
  assert.equal(calls,2)
  cache.advance(15001)
  await cache.cachedLocationMetadata('server:user:years',load)
  assert.equal(calls,3)
})

test('invalidation prevents old requests repopulating the cache; failures can retry', async () => {
  const cache=cacheHarness(), old=deferred()
  const first=cache.cachedLocationMetadata('stats',()=>old.promise)
  cache.invalidateLocationMetadata()
  await cache.cachedLocationMetadata('stats',async()=>2)
  old.resolve(1); await first
  assert.equal(await cache.cachedLocationMetadata('stats',async()=>3),2)
  await assert.rejects(cache.cachedLocationMetadata('failure',async()=>{throw Error('offline')}))
  assert.equal(await cache.cachedLocationMetadata('failure',async()=>4),4)
  cache.observeLocationTasks('user',[{category:'LOCATION',pending:3}])
  const before=cache.locationMetadataRevision.value
  cache.observeLocationTasks('user',[{category:'LOCATION',pending:2}])
  assert.equal(cache.locationMetadataRevision.value,before+1)
})

function pageHarness(service) {
  const source=fs.readFileSync(path.join(root,'views/album/location/LocationList.vue'),'utf8')
  const script=source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm,'')
  let mount, unmount
  const context={ref,computed,watch(){},onMounted:fn=>{mount=fn},onBeforeUnmount:fn=>{unmount=fn},
    defineAsyncComponent:()=>({}),useRouter:()=>({push(){}}),useAppBack:()=>()=>{},
    injectTheme:()=>({isDarkMode:ref(false)}),storeToRefs:x=>x,
    useLocationStore:()=>({level:ref('city'),viewMode:ref('grid'),filterStatus:ref('checked')}),
    onClickOutside(){},locationMetadataRevision:ref(0),locationService:service,
    window:{innerWidth:1280},console:{error(){}},ElMessageBox:{},ElMessage:{}}
  for (const icon of ['Map','LayoutGrid','Clock','Route','BarChart3','Shapes']) context[icon]={}
  vm.createContext(context)
  vm.runInContext(transpile(script+'\nglobalThis.page={fetchLocations,loading,locationsRaw,level};'),context)
  return {...context.page,mount:()=>mount(),unmount:()=>unmount()}
}

test('grid loads without waiting for failed or slow metadata', async () => {
  const stats=deferred(), years=deferred(), places=deferred(), calls=[]
  const page=pageHarness({getStatistics:()=>{calls.push('stats');return stats.promise},getYears:()=>{calls.push('years');return years.promise},getLocations:()=>{calls.push('places');return places.promise}})
  page.mount()
  assert.deepEqual(calls,['stats','years','places'])
  places.resolve([{name:'city'}]); await new Promise(setImmediate)
  assert.equal(page.loading.value,false)
  assert.equal(page.locationsRaw.value[0].name,'city')
  stats.reject(Error('unavailable')); years.resolve([])
  await new Promise(setImmediate)
  assert.equal(page.locationsRaw.value[0].name,'city')
})

test('rapid filters and unmount ignore obsolete location responses', async () => {
  const first=deferred(),second=deferred(),third=deferred(),queue=[first,second,third]
  const page=pageHarness({getLocations:()=>queue.shift().promise})
  const a=page.fetchLocations(),b=page.fetchLocations()
  second.resolve([{name:'latest'}]);await b
  first.resolve([{name:'obsolete'}]);await a
  assert.equal(page.locationsRaw.value[0].name,'latest')
  const c=page.fetchLocations();page.unmount();third.resolve([{name:'closed'}]);await c
  assert.equal(page.locationsRaw.value[0].name,'latest')
})
