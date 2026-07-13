import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

/**
 * 跨进程互斥锁（用于串行化共享可变状态的 e2e 用例）。
 *
 * 背景：Playwright `fullyParallel` 下，不同 worker（独立 Node 进程）会并发跑
 * 同一个 spec 的多个用例。人物相册用例（people-p0/p1）会：
 *   1. 临时改写共享的用户配置 ai.face_recognition_min_photos（lower/restore）；
 *   2. 对真实 identity 做 hide/show/delete/merge/rename 等写操作。
 * 并发时彼此踩踏（min_photos 被提前还原、identity 被别人删掉），导致偶发失败。
 *
 * 该锁用独占创建（O_WRONLY|O_CREAT|O_EXCL）的锁文件实现跨进程互斥，并通过
 * 写入持锁 PID 做 stale 检测——若持锁进程已退出（崩溃/超时），后来者可接管。
 * 所有 people 用例在 beforeEach 获取、afterEach 释放同一把锁，从而全局串行。
 */

const LOCK_DIR = path.join(os.tmpdir(), 'trailsnap-e2e-locks')
try {
  fs.mkdirSync(LOCK_DIR, { recursive: true })
} catch {
  // 多 worker 并发创建目录可能抛 EEXIST，忽略
}

function lockPath(name: string): string {
  // 仅允许字母数字下划线短横，避免路径注入
  const safe = name.replace(/[^A-Za-z0-9_-]/g, '_')
  return path.join(LOCK_DIR, `${safe}.lock`)
}

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

/**
 * 获取名为 `name` 的互斥锁，返回释放函数。超时抛错。
 * 释放函数可安全地多次调用。
 */
export async function acquireMutex(
  name: string,
  timeoutMs = 120_000,
): Promise<() => Promise<void>> {
  const file = lockPath(name)
  const start = Date.now()
  let delay = 50

  for (;;) {
    try {
      const fd = fs.openSync(file, 'wx')
      fs.writeSync(fd, String(process.pid))
      fs.closeSync(fd)
      let released = false
      return async () => {
        if (released) return
        released = true
        try {
          fs.unlinkSync(file)
        } catch {
          // 已被清理或 stale 接管，忽略
        }
      }
    } catch (e) {
      const err = e as NodeJS.ErrnoException
      if (err.code !== 'EEXIST') throw err

      // 锁文件已存在——检测持锁进程是否还活着，死了就接管
      try {
        const pidStr = fs.readFileSync(file, 'utf8').trim()
        const pid = Number(pidStr)
        if (pid && !pidAlive(pid)) {
          fs.unlinkSync(file)
          continue
        }
      } catch {
        // 读失败/解析失败，保持等待
      }

      if (Date.now() - start > timeoutMs) {
        throw new Error(`acquireMutex(${name}) timed out after ${timeoutMs}ms`)
      }
      await new Promise((r) => setTimeout(r, delay))
      delay = Math.min(Math.round(delay * 1.5), 500)
    }
  }
}
