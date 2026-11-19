// Motion and interaction layer for the TrailSnap landing page.
// All listeners are scoped to the component root and torn down on navigation.
export function initHome(root, options = {}) {
  const win = window
  const doc = document
  const body = doc.body
  const controller = new AbortController()
  const listen = (target, name, handler, opts = {}) =>
    target.addEventListener(name, handler, { ...opts, signal: controller.signal })
  const q = (selector) => root.querySelector(selector)
  const qa = (selector) => [...root.querySelectorAll(selector)]
  const reduced = win.matchMedia('(prefers-reduced-motion: reduce)')
  const pinned = win.matchMedia('(min-width: 1001px) and (prefers-reduced-motion: no-preference)')
  const clamp = (value, min = 0, max = 1) => Math.max(min, Math.min(max, value))
  const ease = (value) => value * value * (3 - 2 * value)
  const originalOverflow = body.style.overflow
  let frame = 0
  let disposed = false
  let memoryPage = 0
  const observerList = []

  /* ------------------------------------------------------------------ */
  /* Demo windows: keep the product UI laid out at its native 1440px     */
  /* width on desktop and switch to the product's mobile layout on small */
  /* screens so text never becomes unreadable.                           */
  /* ------------------------------------------------------------------ */
  function fitDesktopPreviews() {
    qa('.desktop-viewport').forEach((viewport) => {
      const frames = [...viewport.querySelectorAll('iframe')]
      const expanded = Boolean(viewport.closest('.expanded'))
      const width = viewport.clientWidth
      const height = viewport.clientHeight
      if (!width || !height) return
      frames.forEach((frame) => {
        if (frame.id === 'city-showcase-frame') {
          frame.style.width = '100%'
          frame.style.height = '100%'
          frame.style.transform = 'none'
          frame.style.setProperty('--preview-scale', '1')
          return
        }
        if (frame.hidden) return
        // Inline previews keep the desktop 1440px canvas on phones so the
        // composition and proportion stay identical to the PC experience.
        // Only the full-screen view falls back to the product's mobile layout,
        // where touch interaction needs readable native controls.
        const native = expanded && win.innerWidth < 768
        if (native) {
          frame.style.width = '100%'
          frame.style.height = '100%'
          frame.style.transform = 'none'
          frame.style.setProperty('--preview-scale', '1')
          return
        }
        const logical = 1440
        const scale = width / logical
        frame.style.width = `${logical}px`
        frame.style.height = `${Math.ceil(height / scale)}px`
        frame.style.transform = `scale(${scale})`
        frame.style.transformOrigin = 'top left'
        frame.style.setProperty('--preview-scale', String(scale))
      })
    })
  }
  const resizeObserver = new ResizeObserver(() => fitDesktopPreviews())
  qa('.desktop-viewport').forEach((viewport) => resizeObserver.observe(viewport))
  observerList.push(resizeObserver)
  listen(win, 'resize', fitDesktopPreviews)
  listen(win, 'resize', () => {
    if (win.innerWidth > 1000) options.closeMenu?.()
  })
  fitDesktopPreviews()

  /* ------------------------------------------------------------------ */
  /* Scroll: progress line, sticky header state, mobile dock, hero drift */
  /* ------------------------------------------------------------------ */
  const progressBar = q('#scroll-progress-bar')
  const heroCopy = q('.hero-copy')
  const heroStage = q('.hero-stage')
  const scrollHint = q('.scroll-hint')

  function onScroll() {
    if (frame) return
    frame = requestAnimationFrame(() => {
      frame = 0
      if (disposed) return
      const y = win.scrollY
      const max = Math.max(1, doc.documentElement.scrollHeight - win.innerHeight)
      if (progressBar) progressBar.style.transform = `scaleX(${clamp(y / max)})`
      root.classList.toggle('is-scrolled', y > 12)
      const nearEnd = y + win.innerHeight > doc.documentElement.scrollHeight - 640
      root.classList.toggle('dock-on', y > 620 && !nearEnd && win.innerWidth < 1001)
      if (!reduced.matches && win.innerWidth > 1000) {
        const drift = clamp(y / Math.max(1, win.innerHeight))
        if (heroCopy) heroCopy.style.setProperty('--hero-y', `${(drift * -34).toFixed(2)}px`)
        if (heroStage) heroStage.style.setProperty('--hero-y', `${(drift * 26).toFixed(2)}px`)
        if (scrollHint) scrollHint.style.opacity = String(clamp(1 - y / 260))
      }
      updateMemoryScene()
    })
  }

  /* ------------------------------------------------------------------ */
  /* Memory scene: pinned on desktop, tab-driven on mobile               */
  /* ------------------------------------------------------------------ */
  const memoryScene = q('.memory-scene')
  const memoryStage = q('.memory-stage')

  function updateMemoryScene() {
    if (!memoryScene || !memoryStage || !pinned.matches) return
    const start = memoryScene.getBoundingClientRect().top + win.scrollY
    const distance = Math.max(1, memoryScene.offsetHeight - memoryStage.offsetHeight)
    const progress = clamp((win.scrollY - start) / distance)
    const index = Math.min(2, Math.floor(progress * 3))
    const fill = progress * 3 - index
    memoryScene.style.setProperty('--memory-progress', String(progress))
    memoryScene.style.setProperty('--chapter-fill', String(clamp(fill, 0.08, 1)))
    if (index !== memoryPage) {
      memoryPage = index
      options.setMemoryPage?.(index)
    }
  }

  function chooseMemory(index) {
    memoryPage = index
    options.setMemoryPage?.(index)
    if (!memoryScene || !memoryStage) return
    if (pinned.matches) {
      const start = memoryScene.getBoundingClientRect().top + win.scrollY
      const distance = Math.max(1, memoryScene.offsetHeight - memoryStage.offsetHeight)
      win.scrollTo({ top: start + distance * (index / 3 + 0.045) + 4, behavior: 'smooth' })
    } else {
      memoryScene.querySelector('.memory-visual')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  /* ------------------------------------------------------------------ */
  /* Fullscreen panels                                                   */
  /* ------------------------------------------------------------------ */
  function closeExpanded() {
    qa('.expanded').forEach((panel) => {
      panel.classList.remove('expanded')
      const button = panel.querySelector('[data-expand]')
      if (button) {
        button.textContent = '全屏查看'
        button.setAttribute('aria-expanded', 'false')
      }
    })
    body.style.overflow = root.classList.contains('menu-open') ? 'hidden' : ''
    fitDesktopPreviews()
  }

  qa('[data-expand]').forEach((button) => {
    listen(button, 'click', () => {
      const panel = root.querySelector('#' + button.dataset.expand)
      if (!panel) return
      const expanded = panel.classList.toggle('expanded')
      button.textContent = expanded ? '退出全屏 ×' : '全屏查看'
      button.setAttribute('aria-expanded', String(expanded))
      body.style.overflow = expanded ? 'hidden' : ''
      if (panel.id === 'live-map-shell') panel.style.width = ''
      requestAnimationFrame(fitDesktopPreviews)
    })
  })

  listen(win, 'keydown', (event) => {
    if (event.key === 'Escape') {
      if (root.classList.contains('menu-open')) {
        options.closeMenu?.()
        return
      }
      if (q('.expanded')) closeExpanded()
    }
  })

  qa('[data-reload]').forEach((button) => {
    listen(button, 'click', () => {
      const target = root.querySelector('#' + button.dataset.reload)
      if (target) target.src = target.getAttribute('src')
    })
  })

  /* ------------------------------------------------------------------ */
  /* Reveal on scroll                                                    */
  /* ------------------------------------------------------------------ */
  if (!reduced.matches && 'IntersectionObserver' in win) {
    root.classList.add('reveal-ready')
    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-in')
            revealObserver.unobserve(entry.target)
          }
        })
      },
      { rootMargin: '0px 0px -12% 0px', threshold: 0.08 },
    )
    qa('[data-reveal]').forEach((element) => revealObserver.observe(element))
    observerList.push(revealObserver)
  }

  /* ------------------------------------------------------------------ */
  /* Section rail                                                        */
  /* ------------------------------------------------------------------ */
  const railLinks = qa('[data-rail]')
  if (railLinks.length && 'IntersectionObserver' in win) {
    const railObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          const id = entry.target.id
          railLinks.forEach((link) => link.classList.toggle('is-active', link.dataset.rail === id))
        })
      },
      { rootMargin: '-42% 0px -50% 0px', threshold: 0 },
    )
    railLinks.forEach((link) => {
      const section = root.querySelector('#' + link.dataset.rail)
      if (section) railObserver.observe(section)
    })
    observerList.push(railObserver)
  }

  /* ------------------------------------------------------------------ */
  /* Search demo: a quiet typewriter in the capability card              */
  /* ------------------------------------------------------------------ */
  const typed = q('#search-typed')
  const queries = ['海边看日落的照片', '去年冬天，山里的雪', '和家人一起的晚餐', '在湖边散步的下午']
  let typeTimer = 0
  let queryIndex = 0
  let charIndex = 0
  let deleting = false
  let typing = false
  let typeStarted = false

  function typeLoop() {
    if (disposed || !typed) return
    const query = queries[queryIndex]
    if (!deleting) {
      charIndex += 1
      typed.textContent = query.slice(0, charIndex)
      if (charIndex >= query.length) {
        deleting = true
        typeTimer = win.setTimeout(typeLoop, 2400)
        return
      }
      typeTimer = win.setTimeout(typeLoop, 80 + Math.random() * 70)
    } else {
      charIndex -= 2
      typed.textContent = query.slice(0, Math.max(0, charIndex))
      if (charIndex <= 0) {
        deleting = false
        queryIndex = (queryIndex + 1) % queries.length
        typeTimer = win.setTimeout(typeLoop, 420)
        return
      }
      typeTimer = win.setTimeout(typeLoop, 34)
    }
  }

  if (typed && !reduced.matches) {
    const searchCard = typed.closest('.cap-search')
    if (searchCard && 'IntersectionObserver' in win) {
      const typeObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting && !typing) {
              typing = true
              if (!typeStarted) {
                typeStarted = true
                charIndex = queries[0].length
                deleting = true
                typeTimer = win.setTimeout(typeLoop, 1200)
              } else {
                typeLoop()
              }
            } else if (!entry.isIntersecting && typing) {
              typing = false
              win.clearTimeout(typeTimer)
            }
          })
        },
        { threshold: 0.2 },
      )
      typeObserver.observe(searchCard)
      observerList.push(typeObserver)
    }
  }

  /* ------------------------------------------------------------------ */
  /* Pointer light: cards and the hero atmosphere                        */
  /* ------------------------------------------------------------------ */
  if (win.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    qa('[data-spotlight]').forEach((card) => {
      listen(card, 'pointermove', (event) => {
        const rect = card.getBoundingClientRect()
        card.style.setProperty('--mx', `${event.clientX - rect.left}px`)
        card.style.setProperty('--my', `${event.clientY - rect.top}px`)
      })
    })

    const hero = q('.hero')
    if (hero) {
      listen(hero, 'pointermove', (event) => {
        const rect = hero.getBoundingClientRect()
        hero.style.setProperty('--px', `${((event.clientX - rect.left) / rect.width - 0.5).toFixed(3)}`)
        hero.style.setProperty('--py', `${((event.clientY - rect.top) / rect.height - 0.5).toFixed(3)}`)
      })
      listen(hero, 'pointerleave', () => {
        hero.style.setProperty('--px', '0')
        hero.style.setProperty('--py', '0')
      })
    }
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                                */
  /* ------------------------------------------------------------------ */
  listen(win, 'scroll', onScroll, { passive: true })
  listen(win, 'load', fitDesktopPreviews)
  listen(reduced, 'change', () => {
    root.classList.remove('reveal-ready')
    onScroll()
  })
  listen(pinned, 'change', () => {
    memoryScene?.style.setProperty('--memory-progress', '0')
    onScroll()
  })

  // Run once after layout settles and again once fonts are ready.
  requestAnimationFrame(() => {
    onScroll()
    fitDesktopPreviews()
  })
  if (doc.fonts?.ready) doc.fonts.ready.then(() => { if (!disposed) fitDesktopPreviews() })

  return {
    refresh() {
      requestAnimationFrame(() => {
        fitDesktopPreviews()
        updateMemoryScene()
      })
    },
    chooseMemory,
    destroy() {
      disposed = true
      controller.abort()
      observerList.forEach((observer) => observer.disconnect())
      win.clearTimeout(typeTimer)
      cancelAnimationFrame(frame)
      root.classList.remove('reveal-ready', 'is-scrolled', 'dock-on')
      body.style.overflow = originalOverflow
    },
  }
}