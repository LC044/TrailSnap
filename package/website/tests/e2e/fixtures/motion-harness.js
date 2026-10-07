import { createRouter, createMemoryHistory } from 'vue-router';
    import { createApp, ref, h, KeepAlive } from 'vue';
    import Menu from '/src/components/ui/AdaptiveMenu.vue';
    import Dialog from '/src/components/ui/ResponsiveDialog.vue';
    import { registerButtonMotion } from '/src/composables/useButtonMotion.ts';
    import { useAnchoredSheet } from '/src/composables/useAnchoredSheet.ts';
    import '/src/style.css'; import '/src/styles/ui.css';
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/motion/:page', component: { render: () => null } }] });
    await router.push('/motion/one');
    window.fixtureRouter = router;
    const away = ref(false);
    window.fixtureNavigation = away;
    const Surface = { setup() {
      const menu = ref(false), menu2 = ref(false), sheet = ref(false);
      const anchored = useAnchoredSheet(230, () => [62, 230, 600], ref(true));
      window.fixtureState = { menu, menu2, sheet };
      return () => h('main', { style: 'padding:40px' }, [
        h('div', { id: 'capsule', class: 'ts-liquid-glass ts-glass-toolbar', style: 'display:flex;width:fit-content;margin-left:auto' }, [
          h('button', { id: 'capsule-other', class: 'ts-glass-button', 'aria-expanded': menu2.value, onClick: () => menu2.value = !menu2.value }, 'A'),
          h(Menu, { modelValue: menu2.value, 'onUpdate:modelValue': value => menu2.value = value, title: '菜单二', mobilePresentation: 'popover' }, { default: () => h('button', { class: 'ts-action-row' }, '第二组操作') }),
          h('button', { id: 'menu-trigger', class: 'ts-button ts-button-secondary', 'aria-expanded': menu.value, onClick: () => menu.value = !menu.value }, '更多操作'),
          h(Menu, { modelValue: menu.value, 'onUpdate:modelValue': value => menu.value = value, title: '菜单', mobilePresentation: 'popover' }, { default: () => [h('button', { class: 'ts-action-row' }, '动作一'), h('button', { class: 'ts-action-row' }, '动作二')] })
        ]),
        h('button', { id: 'sheet-trigger', class: 'ts-button ts-button-primary', onClick: () => sheet.value = true }, '打开抽屉'),
        h('button', { id: 'disabled', class: 'ts-button', disabled: true }, '禁用'),
        h(Dialog, { modelValue: sheet.value, 'onUpdate:modelValue': value => sheet.value = value, title: '抽屉' }, { default: () => h('div', { style: 'height:220px' }, '可滚动内容') }),
        h('aside', { id: 'anchored-sheet', style: { position: 'fixed', bottom: '0', width: '250px', height: anchored.height.value + 'px', background: 'var(--ts-color-surface)' } }, [h('div', { id: 'anchored-handle', style: 'height:32px;touch-action:none', onPointerdown: anchored.start, onClick: anchored.toggle }, '拖动')])
      ]);
    } };
    const Away = { render: () => h('div', { id: 'away-page' }, '另一个页面') };
    createApp({ setup: () => () => h(KeepAlive, null, { default: () => away.value ? h(Away) : h(Surface) }) }).use(router).mount('#fixture');
    registerButtonMotion();
