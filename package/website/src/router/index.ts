// src/router/index.ts
import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';

// 路由懒加载（优化首屏性能，TS 自动推断类型）
const HomePage = () => import('@/views/HomePage.vue');
// const AlbumPage = () => import('@/views/AlbumPage.vue');
const AlbumList = () => import('@/views/album/AlbumList.vue');
const AlbumDetail = () => import('@/views/album/AlbumDetail.vue');
const PhotosPage = () => import('@/views/PhotosPage.vue');
const TicketPage = () => import('@/views/ticket/TicketPage.vue');
const StatisticsPage = () => import('@/views/ticket/StatisticsPage.vue');
const Settings = () => import('@/views/Settings.vue');
const PeopleList = () => import('@/views/album/people/PeopleList.vue');
const PeopleDetail = () => import('@/views/album/people/PeopleDetail.vue');
const LocationList = () => import('@/views/album/location/LocationList.vue');
const LocationDetail = () => import('@/views/album/location/LocationDetail.vue');
const ClassificationList = () => import('@/views/album/intelligent-classification/ClassificationList.vue');
const ClassificationDetail = () => import('@/views/album/intelligent-classification/ClassificationDetail.vue');
const SearchResult = () => import('@/views/search/SearchResult.vue');
const MobileSearch = () => import('@/views/search/MobileSearch.vue');
const CleanupPage = () => import('@/views/toolbox/CleanupPage.vue');
const ToolboxPage = () => import('@/views/toolbox/ToolboxPage.vue');
const SimilarPhotoCleanup = () => import('@/views/toolbox/SimilarPhotoCleanup.vue');
const DuplicatePhotoCleanup = () => import('@/views/toolbox/DuplicatePhotoCleanup.vue');
const TicketEdit = () => import('@/views/More.vue');
const RecycleBinPage = () => import('@/views/RecycleBinPage.vue');

const NotFound = () => import('@/views/NotFound.vue');

// 路由配置：TS 类型为 RouteRecordRaw 数组，强制类型校验
const routes: RouteRecordRaw[] = [
  // 主布局组：所有子页面都使用 MainLayout
  {
    path: '/',
    component: () => import('@/components/RouteOutlet.vue'),
    meta: { layout: 'main' }, // 标记布局类型（供 App.vue 识别）
    children: [
      { path: '', name: 'Home', component: HomePage, meta: { title: '首页' } },
      { path: '/album', name: 'AlbumList', component: AlbumList, meta: { title: '智能相册' } },
      { path: '/album/:id', name: 'AlbumDetail', component: AlbumDetail, meta: { title: '相册详情' } },
      { path: '/album/people', name: 'PeopleList', component: PeopleList, meta: { title: '人物相册' } },
      { path: '/album/people/:id', name: 'PeopleDetail', component: PeopleDetail, meta: { title: '人物详情' } },
      { path: '/album/location', name: 'LocationList', component: LocationList, meta: { title: '位置相册' } },
      { path: '/album/location/:name', name: 'LocationDetail', component: LocationDetail, meta: { title: '位置详情' } },
      { path: '/album/classification', name: 'ClassificationList', component: ClassificationList, meta: { title: '智能分类' } },
      { path: '/album/classification/:name', name: 'ClassificationDetail', component: ClassificationDetail, meta: { title: '分类详情' } },
      { path: '/search', name: 'SearchResult', component: SearchResult, meta: { title: '搜索结果' } },
      { path: '/toolbox', name: 'Toolbox', component: ToolboxPage, meta: { title: '工具箱' } },
      { path: '/toolbox/similar', name: 'SimilarPhotoCleanup', component: SimilarPhotoCleanup, meta: { title: '相似照片清理' } },
      { path: '/toolbox/duplicate', name: 'DuplicatePhotoCleanup', component: DuplicatePhotoCleanup, meta: { title: '重复照片清理' } },
      { path: '/toolbox/organize', name: 'OrganizePhotos', component: () => import('@/views/toolbox/OrganizePage.vue'), meta: { title: '图片文件整理' } },
      { path: '/toolbox/rename', name: 'BatchRename', component: () => import('@/views/toolbox/RenamePage.vue'), meta: { title: '批量重命名' } },
      { path: '/toolbox/time-from-filename', name: 'TimeFromFilename', component: () => import('@/views/toolbox/TimeFromFilenamePage.vue'), meta: { title: '从文件名修改拍摄信息' } },
      { path: '/toolbox/cleanup', name: 'ToolboxCleanup', component: CleanupPage, meta: { title: '清理相册' } },
      { path: '/toolbox/ticket-edit', name: 'TicketEdit', component: TicketEdit, meta: { title: '车票编辑' } },
      { path: '/recycle-bin', name: 'RecycleBin', component: RecycleBinPage, meta: { title: '回收站' } },
      { path: '/photos', name: 'Photos', component: PhotosPage, meta: { title: '所有照片' } },
      { path: '/mobile-search', name: 'MobileSearch', component: MobileSearch, meta: { title: '搜索', layout: 'blank' } },
      { path: '/ticket', name: 'Ticket', component: TicketPage, meta: { title: '车票', keepAlive: true } },
      { path: '/statistics', name: 'Statistics', component: StatisticsPage, meta: { title: '统计' } },
      { path: '/settings', name: 'Settings', component: Settings, meta: { title: '设置' } },
    ],
  },

  // Annual Report (Standalone Layout)
  {
    path: '/annual-report',
    name: 'AnnualReport',
    component: () => import('@/views/annual-report/index.vue'),
    meta: { layout: 'blank', title: '年度回忆录' },
  },

  // 登录页面（使用空白布局）
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { layout: 'blank', title: '登录' },
  },

  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/login/Register.vue'),
    meta: { layout: 'blank', title: '注册' },
  },

  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('@/views/login/ForgotPassword.vue'),
    meta: { layout: 'blank', title: '找回密码' },
  },

  // 404 页面（使用空白布局）
  {
    path: '/:pathMatch(.*)*', // 匹配所有未定义路由
    name: 'NotFound',
    component: NotFound,
    meta: { layout: 'blank', title: '页面未找到' },
  },
];

// 创建路由实例
const router = createRouter({
  //history: createWebHistory(import.meta.env.BASE_URL), // 读取环境变量中的基础路径
  history: createWebHistory(),
  routes,
  // 可选：路由切换时滚动到顶部
  scrollBehavior: () => ({ top: 0 }),
});

import { useUserStore } from '@/stores/user';

// 可选：路由守卫 - 动态设置页面标题
router.beforeEach((to, from, next) => {
  if (to.meta.title) {
    document.title = to.meta.title as string;
  }

  const userStore = useUserStore();
  const whiteList = ['/login', '/register', '/forgot-password', '/404'];

  if (userStore.token) {
    if (to.path === '/login') {
      next({ path: '/' });
    } else {
      next();
    }
  } else {
    if (whiteList.includes(to.path) || to.path.startsWith('/annual-report')) { // Allow annual report for now or specific public pages
      next();
    } else {
      next(`/login?redirect=${to.fullPath}`);
    }
  }
});

export default router;
