/**
 * Composable for animated number counting effect
 */
import { ref, watch, onUnmounted } from 'vue'

/**
 * Creates an animated number that smoothly transitions to target values
 * @param {import('vue').Ref<number>} targetValue - Reactive reference to the target value
 * @param {Object} options - Animation options
 * @param {number} options.duration - Animation duration in milliseconds (default: 1200)
 * @param {boolean} options.immediate - Start animation immediately (default: true)
 * @returns {import('vue').Ref<number>} Animated display value
 */
export function useAnimatedNumber(targetValue, options = {}) {
  const { duration = 1200, immediate = true } = options

  const displayValue = ref(0)
  let animationFrame = null

  /**
   * Easing function - ease-out cubic for smooth deceleration
   * @param {number} t - Progress (0-1)
   * @returns {number} Eased progress
   */
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3)
  }

  /**
   * Animate from current value to target
   * @param {number} target - Target value
   */
  function animate(target) {
    if (animationFrame) {
      cancelAnimationFrame(animationFrame)
    }

    const start = displayValue.value
    const change = target - start

    if (Math.abs(change) < 1) {
      displayValue.value = target
      return
    }

    const startTime = performance.now()

    function step(currentTime) {
      const elapsed = currentTime - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = easeOutCubic(progress)

      displayValue.value = Math.round(start + change * eased)

      if (progress < 1) {
        animationFrame = requestAnimationFrame(step)
      } else {
        displayValue.value = target
      }
    }

    animationFrame = requestAnimationFrame(step)
  }

  // Watch for changes in target value
  watch(
    targetValue,
    (newVal) => {
      const num = Number(newVal)
      if (Number.isFinite(num)) {
        animate(num)
      }
    },
    { immediate }
  )

  // Cleanup on unmount
  onUnmounted(() => {
    if (animationFrame) {
      cancelAnimationFrame(animationFrame)
    }
  })

  return displayValue
}

/**
 * Creates multiple animated numbers from an object of refs
 * @param {Object<string, import('vue').Ref<number>>} targets - Object with named target refs
 * @param {Object} options - Animation options (shared)
 * @returns {Object<string, import('vue').Ref<number>>} Object with animated values
 */
export function useAnimatedNumbers(targets, options = {}) {
  const animated = {}

  for (const [key, targetRef] of Object.entries(targets)) {
    animated[key] = useAnimatedNumber(targetRef, options)
  }

  return animated
}
