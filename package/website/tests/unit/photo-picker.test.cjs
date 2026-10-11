const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

function load(filename, dependencies) {
  let source = fs.readFileSync(path.resolve(__dirname, '../../src', filename), 'utf8')
  if (filename.endsWith('.vue')) source = compiler.compileScript(compiler.parse(source).descriptor, {id: filename}).content
  source = source.replaceAll('import.meta.url', "'file:///profile.vue'")
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText
  const module = {exports:{}}
  vm.runInThisContext('(function(require,module,exports){' + code + '\n})', {filename})(
    name => { if(name === 'vue') return vue; if(name in dependencies) return dependencies[name]; throw new Error(name) },
    module, module.exports,
  )
  return module.exports
}
const renderer = vue.createRenderer({
  insert(){}, remove(){}, createElement:()=>({}), createText:()=>({}), createComment:()=>({}),
  setText(){}, setElementText(){}, parentNode:()=>null, nextSibling:()=>null, patchProp(){},
})
function mount(component, props = {}, emit = () => {}) {
  let state
  const app = renderer.createApp({setup(){state=component.setup(props, {expose(){},emit});return()=>null}})
  app.mount({})
  return {state, unmount:()=>app.unmount()}
}
const deferred = () => {let resolve; const promise = new Promise(r=>resolve=r); return {promise,resolve}}

function profile(update) {
  const user = {id:'u',username:'trailsnap',nickname:'原昵称',email:'',avatar:'old'}
  const store = {userInfo:user,updateUserInfo(data){this.userInfo={...this.userInfo,...data}},getUserInfo:async()=>user}
  const errors = []
  const component = load('views/settings/ProfileSettings.vue', {
    'element-plus':{ElMessage:{success(){},error:msg=>errors.push(msg)}},
    '@/stores/user':{useUserStore:()=>store},
    '@/stores/selectionStore':{useSelectionStore:()=>({})},
    '@/api/user':{userService:{updateCurrentUser:update}},
    '@/components/PhotoSelectorDialog.vue':{},
    '@/utils/request':{},
    '@/config/server':{toServerUrl:x=>x},
    '@/utils/mediaUrl':{thumbnailPath:id=>'/thumb/'+id},
  }).default
  return {...mount(component),store,errors}
}
test('gallery avatar saves immediately, updates account UI, and preserves the nickname draft', async()=>{
  const pending=deferred(), calls=[]
  const ctx=profile(params=>{calls.push(params);return pending.promise})
  ctx.state.form.nickname='未保存草稿'
  ctx.state.showGallerySelector.value=true
  const save=ctx.state.handleSelectFromGallery(['new-photo'])
  assert.deepEqual(calls,[{avatar:'/thumb/new-photo'}])
  assert.equal(ctx.state.savingAvatar.value,true)
  assert.equal(ctx.state.form.avatar,'old')
  await ctx.state.handleSelectFromGallery(['duplicate'])
  assert.equal(calls.length,1)
  pending.resolve({avatar:'/thumb/new-photo'})
  await save
  assert.equal(ctx.state.form.avatar,'/thumb/new-photo')
  assert.equal(ctx.store.userInfo.avatar,'/thumb/new-photo')
  assert.equal(ctx.state.form.nickname,'未保存草稿')
  assert.equal(ctx.state.showGallerySelector.value,false)
  ctx.unmount()
})
test('failed avatar save keeps the old avatar and selector open for retry', async()=>{
  const ctx=profile(async()=>{throw new Error('offline')})
  ctx.state.showGallerySelector.value=true
  await ctx.state.handleSelectFromGallery(['new-photo'])
  assert.equal(ctx.state.form.avatar,'old')
  assert.equal(ctx.store.userInfo.avatar,'old')
  assert.equal(ctx.state.showGallerySelector.value,true)
  assert.equal(ctx.state.savingAvatar.value,false)
  assert.equal(ctx.errors.length,1)
  ctx.unmount()
})
function identityStore(getIdentityPhotos) {
  return load('stores/identityPhotoSelectionStore.ts',{
    pinia:{defineStore:(_id,setup)=>setup},
    '@/api/face':{faceApi:{getIdentityPhotos}},
    '@/stores/photoStore':{mapPhotoToImage:p=>p},
  }).useIdentityPhotoSelectionStore()
}
test('person cover picker loads photos beyond the first page',async()=>{
  const calls=[]
  const store=identityStore(async(id,page,limit)=>{
    calls.push([id,page,limit])
    return page===1?Array.from({length:100},(_,i)=>({id:String(i)})):[{id:'last'}]
  })
  store.setIdentity('person')
  await store.loadPhotos(true)
  await store.loadPhotos()
  assert.equal(store.images.value.length,101)
  assert.equal(store.hasMore.value,false)
  assert.deepEqual(calls,[['person',1,100],['person',2,100]])
})
test('switching person rejects stale cover candidates from the previous request',async()=>{
  const pending=deferred()
  const store=identityStore(id=>id==='old'?pending.promise:Promise.resolve([{id:'new-photo'}]))
  store.setIdentity('old')
  const old=store.loadPhotos()
  store.setIdentity('new')
  await store.loadPhotos()
  pending.resolve([{id:'old-photo'}])
  await old
  assert.deepEqual(store.images.value.map(p=>p.id),['new-photo'])
})
function pickerSearchStore(searchByText, getAllPhotos = async(_skip,_limit,{ids})=>ids.map(id=>({id}))) {
  return load('stores/photoPickerSearchStore.ts',{
    pinia:{defineStore:(_id,setup)=>setup},
    '@/api/search':{default:{searchByText},__esModule:true},
    '@/api/album':{albumService:{getAllPhotos}},
    '@/stores/photoStore':{mapPhotoToImage:p=>p},
    '@/utils/date':load('utils/date.ts',{}),
  }).usePhotoPickerSearchStore()
}
test('picker search filters scoped candidates on the server and keeps search rank order',async()=>{
  const calls=[]
  const store=pickerSearchStore(async()=>['a','b','c'].map(id=>({photo:{id}})),async(skip,limit,filters)=>{
    calls.push(filters)
    return [{id:'c'},{id:'a'}]
  })
  await store.search('旅行','filename',{face_id:'person'})
  assert.deepEqual(calls,[{face_id:'person',ids:['a','b','c']}])
  assert.deepEqual(store.images.value.map(p=>p.id),['a','c'])
  assert.equal(store.hasMore.value,false)
})
test('picker search continues through an empty scoped page and paginates without losing existing results',async()=>{
  const calls=[]
  const store=pickerSearchStore(async({skip})=>{
    calls.push(skip)
    return skip<120?Array.from({length:60},(_,i)=>({photo:{id:String(skip+i)}})):[{photo:{id:'last'}}]
  },async(_skip,_limit,filters)=>filters.ids[0]==='0'?[]:filters.ids.map(id=>({id})))
  await store.search('关键词','location',{province:'浙江省'})
  assert.deepEqual(calls,[0,60])
  assert.equal(store.images.value.length,60)
  await store.loadPhotos()
  assert.deepEqual(calls,[0,60,120])
  assert.equal(store.images.value.length,61)
  assert.equal(store.images.value[60].id,'last')
})
test('clearing or replacing a search rejects stale responses',async()=>{
  const pending=deferred()
  const store=pickerSearchStore(({text})=>text==='old'?pending.promise:Promise.resolve([{photo:{id:'new'}}]))
  const old=store.search('old','filename')
  await store.search('new','filename')
  pending.resolve([{photo:{id:'old'}}])
  await old
  assert.deepEqual(store.images.value.map(p=>p.id),['new'])
  store.resetAll()
  assert.equal(store.query.value,'')
  assert.deepEqual(store.images.value,[])
})
test('failed picker search retries the same page instead of skipping it',async()=>{
  const calls=[]
  const store=pickerSearchStore(async({skip})=>{
    calls.push(skip)
    if(calls.length===1) throw new Error('offline')
    return [{photo:{id:'retry'}}]
  })
  await store.search('photo','filename')
  assert.ok(store.error.value)
  await store.loadPhotos()
  assert.deepEqual(calls,[0,0])
  assert.deepEqual(store.images.value.map(p=>p.id),['retry'])
  assert.equal(store.error.value,null)
})

test('unscoped picker search also removes candidates outside the active photo library',async()=>{
  const store=pickerSearchStore(async()=>['active','deleted'].map(id=>({photo:{id}})),async()=>[{id:'active'}])
  await store.search('photo','filename')
  assert.deepEqual(store.images.value.map(p=>p.id),['active'])
})

test('picker date search uses the same date range and threshold as existing search results',async()=>{
  let request
  const store=pickerSearchStore(async params=>{request=params;return []})
  await store.search('2026年10月','date')
  assert.equal(request.text,'')
  assert.equal(request.type,'date')
  assert.equal(request.start_time,'2026-10-01T00:00:00Z')
  assert.equal(request.end_time,'2026-10-31T23:59:59Z')
  assert.equal(request.threshold,0.22)
})

function sharedSearch(embedded) {
  const navigations=[],events=[],history=[]
  const component=load('views/search/MobileSearch.vue',{
    '@/components/ui/BackButton.vue':{},
    'vue-router':{useRouter:()=>({push:value=>navigations.push(value),replace:value=>navigations.push(value)})},
    'lucide-vue-next':{},
    '@vueuse/core':{useDebounceFn:fn=>fn},
    '@/api/search':{default:{getSuggestions:async()=>[]},__esModule:true},
    '@/utils/date':load('utils/date.ts',{}),
    '@/components/ui/IconButton.vue':{},
    '@/composables/useAppBack':{useAppBack:()=>()=>{}},
    '@/stores/uiStore':{useUiStore:()=>({openAgent(){}})},
    '@/stores/searchStore':{useSearchStore:()=>({history,remember:q=>history.push(q),clearHistory(){}})},
    '@/stores/albumStore':{useAlbumStore:()=>({fetchSmartAlbumOverview:async()=>{}})},
    '@/utils/mediaUrl':{thumbnailUrl:()=>''},
    '@/components/SmartAlbumCover.vue':{},
  }).default
  return {...mount(component,{embedded},(name,value)=>events.push({name,value})),navigations,events,history}
}
test('embedded existing search emits date and semantic criteria without leaving the picker',()=>{
  const ctx=sharedSearch(true)
  ctx.state.searchText.value='2026年10月'
  ctx.state.handleSearch()
  ctx.state.runExample('春天的旅行')
  assert.deepEqual(ctx.events,[
    {name:'search',value:{query:'2026年10月',type:'date'}},
    {name:'search',value:{query:'春天的旅行',type:undefined}},
  ])
  assert.equal(ctx.navigations.length,0)
  assert.deepEqual(ctx.history,['2026年10月','春天的旅行'])
  ctx.unmount()
})
test('embedded search suggestions and representative cards return existing metadata search types',()=>{
  const ctx=sharedSearch(true)
  ctx.state.selectSuggestion({type:'ocr',value:'车票',label:'照片文字'})
  ctx.state.openRepresentative('people','/album/people',{entity_id:'person',name:'小明'})
  assert.deepEqual(ctx.events,[
    {name:'search',value:{query:'车票',type:'ocr'}},
    {name:'search',value:{query:'小明',type:'person'}},
  ])
  assert.equal(ctx.navigations.length,0)
  ctx.unmount()
})
test('normal existing search still navigates to the original result route',()=>{
  const ctx=sharedSearch(false)
  ctx.state.searchText.value='杭州'
  ctx.state.handleSearch()
  ctx.state.selectSuggestion({type:'location',value:'杭州市',label:'地点'})
  assert.deepEqual(ctx.navigations,[
    {path:'/search',query:{q:'杭州'}},
    {path:'/search',query:{q:'杭州市',type:'location'}},
  ])
  assert.equal(ctx.events.length,0)
  ctx.unmount()
})
