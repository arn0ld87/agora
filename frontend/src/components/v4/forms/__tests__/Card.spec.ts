import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Card from '../Card.vue'

describe('Card', () => {
  it('renders default slot content', () => {
    const w = mount(Card, { slots: { default: '<p>Body content</p>' } })
    expect(w.find('.v4-card__body').html()).toContain('Body content')
  })

  it('renders title and subtitle when provided', () => {
    const w = mount(Card, {
      props: { title: 'Mein Titel', subtitle: 'Untertitel' },
    })
    expect(w.find('.v4-card__title').text()).toBe('Mein Titel')
    expect(w.find('.v4-card__subtitle').text()).toBe('Untertitel')
  })

  it('omits header when neither title nor right slot provided', () => {
    const w = mount(Card, { slots: { default: 'Body' } })
    expect(w.find('.v4-card__header').exists()).toBe(false)
  })

  it('shows header when only right slot given', () => {
    const w = mount(Card, {
      slots: { right: '<button>Action</button>' },
    })
    expect(w.find('.v4-card__header').exists()).toBe(true)
    expect(w.find('.v4-card__right').html()).toContain('Action')
  })

  it('applies custom pad via inline style', () => {
    const w = mount(Card, { props: { pad: 32 } })
    expect(w.find('.v4-card').attributes('style')).toContain('padding: 32px')
  })

  it('renders footer slot', () => {
    const w = mount(Card, {
      slots: { footer: '<span>Footer</span>' },
    })
    expect(w.find('.v4-card__footer').text()).toBe('Footer')
  })

  it('adds header margin--with-subtitle class when subtitle set', () => {
    const w = mount(Card, { props: { title: 'T', subtitle: 'S' } })
    expect(w.find('.v4-card__header').classes()).toContain('v4-card__header--with-subtitle')
  })
})
