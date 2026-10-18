// Shared by the router and idle preloader. Importing a module never mounts a page.
export const HomePage = () => import('@/views/HomePage.vue')
export const PhotosPage = () => import('@/views/PhotosPage.vue')
export const AlbumList = () => import('@/views/album/AlbumList.vue')
export const TicketPage = () => import('@/views/ticket/TicketPage.vue')

export const commonPageLoaders = [PhotosPage, AlbumList, TicketPage]
