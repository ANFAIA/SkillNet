import { describe, it, expect } from 'vitest'
import {
  ease,
  duration,
  spring,
  transition,
  pageTransition,
  contentSwap,
  staggerContainer,
  staggerItem,
  slideVariants,
  backdrop,
  sidebarSlide,
} from './motion'

describe('motion presets', () => {
  describe('ease curves', () => {
    it('exports base easing as a 4-element tuple', () => {
      expect(ease.base).toHaveLength(4)
      expect(ease.base[0]).toBeTypeOf('number')
    })

    it('bounce easing has overshoot (4th value > 1)', () => {
      expect(ease.bounce[3]).toBeGreaterThan(1)
    })
  })

  describe('durations', () => {
    it('are in ascending order', () => {
      expect(duration.instant).toBeLessThan(duration.fast)
      expect(duration.fast).toBeLessThan(duration.normal)
      expect(duration.normal).toBeLessThan(duration.medium)
      expect(duration.medium).toBeLessThan(duration.slow)
      expect(duration.slow).toBeLessThan(duration.morphSlow)
    })

    it('instant is under 200ms', () => {
      expect(duration.instant).toBeLessThan(0.2)
    })
  })

  describe('springs', () => {
    it('all have type "spring"', () => {
      for (const key of Object.keys(spring) as (keyof typeof spring)[]) {
        expect(spring[key].type).toBe('spring')
      }
    })

    it('stiff spring has higher stiffness than gentle', () => {
      expect(spring.stiff.stiffness).toBeGreaterThan(spring.gentle.stiffness)
    })
  })

  describe('transition presets', () => {
    it('page transition uses duration.normal', () => {
      expect(transition.page.duration).toBe(duration.normal)
    })

    it('micro transition is a spring', () => {
      expect(transition.micro.type).toBe('spring')
    })
  })

  describe('animation states', () => {
    it('pageTransition starts and exits at opacity 0', () => {
      expect(pageTransition.initial.opacity).toBe(0)
      expect(pageTransition.exit.opacity).toBe(0)
      expect(pageTransition.animate.opacity).toBe(1)
    })

    it('contentSwap includes Y offset', () => {
      expect(contentSwap.initial.y).toBe(8)
      expect(contentSwap.exit.y).toBe(-8)
      expect(contentSwap.animate.y).toBe(0)
    })

    it('staggerContainer staggers children', () => {
      expect(
        staggerContainer.visible.transition.staggerChildren,
      ).toBeGreaterThan(0)
    })

    it('staggerItem animates from hidden to visible', () => {
      expect(staggerItem.hidden.opacity).toBe(0)
      expect(staggerItem.visible.opacity).toBe(1)
    })
  })

  describe('slideVariants()', () => {
    it('returns enter/center/exit variants', () => {
      const v = slideVariants(100)
      expect(v).toHaveProperty('enter')
      expect(v).toHaveProperty('center')
      expect(v).toHaveProperty('exit')
    })

    it('enter slides from positive direction for dir=1', () => {
      const v = slideVariants(80)
      const enterState = v.enter(1)
      expect(enterState.x).toBe(80)
      expect(enterState.opacity).toBe(0)
    })

    it('enter slides from negative direction for dir=-1', () => {
      const v = slideVariants(80)
      const enterState = v.enter(-1)
      expect(enterState.x).toBe(-80)
    })

    it('center has full opacity and x=0', () => {
      const v = slideVariants()
      expect(v.center.opacity).toBe(1)
      expect(v.center.x).toBe(0)
    })

    it('accepts string distance values', () => {
      const v = slideVariants('100%')
      const enterState = v.enter(1)
      expect(enterState.x).toBe('100%')
    })
  })

  describe('overlay presets', () => {
    it('backdrop fades in from opacity 0', () => {
      expect(backdrop.initial.opacity).toBe(0)
      expect(backdrop.animate.opacity).toBe(1)
    })

    it('sidebarSlide starts off-screen left', () => {
      expect(sidebarSlide.initial.x).toBe('-100%')
      expect(sidebarSlide.animate.x).toBe(0)
    })
  })
})
