import { watch, onBeforeUnmount, type Ref } from "vue";
const locks = new Map<HTMLElement, { count: number; overflow: string }>();
/** Nested dialogs share locks so closing a child cannot unlock the parent. */
export function useModalScrollLock(visible: Ref<boolean>) {
  let elements: HTMLElement[] = [];
  const release = () => {
    for (const element of elements) {
      const lock = locks.get(element);
      if (!lock) continue;
      if (--lock.count === 0) {
        element.style.overflow = lock.overflow;
        locks.delete(element);
      }
    }
    elements = [];
  };
  watch(
    visible,
    (value) => {
      release();
      if (!value || typeof document === "undefined") return;
      elements = [
        document.body,
        ...Array.from(
          document.querySelectorAll<HTMLElement>(".ts-main-scroll"),
        ),
      ];
      for (const element of elements) {
        const lock = locks.get(element);
        if (lock) lock.count++;
        else {
          locks.set(element, { count: 1, overflow: element.style.overflow });
          element.style.overflow = "hidden";
        }
      }
    },
    { immediate: true },
  );
  onBeforeUnmount(release);
}
