// Issue #130 / SUB3 — Mention/Hashtag-Tokenizer.

import { describe, it, expect } from 'vitest'

import { tokenizeFeedText } from '../feedHighlight'

describe('tokenizeFeedText', () => {
  it('liefert leeres Array für falsy Input', () => {
    expect(tokenizeFeedText('')).toEqual([])
    expect(tokenizeFeedText(null)).toEqual([])
    expect(tokenizeFeedText(undefined)).toEqual([])
  })

  it('liefert nur einen Text-Token, wenn keine Mentions/Hashtags', () => {
    expect(tokenizeFeedText('Reiner Text ohne Marker.')).toEqual([
      { type: 'text', value: 'Reiner Text ohne Marker.' },
    ])
  })

  it('erkennt eine Mention', () => {
    expect(tokenizeFeedText('Hallo @alex!')).toEqual([
      { type: 'text', value: 'Hallo ' },
      { type: 'mention', value: '@alex' },
      { type: 'text', value: '!' },
    ])
  })

  it('erkennt einen Hashtag', () => {
    expect(tokenizeFeedText('Trend #klimakrise heute.')).toEqual([
      { type: 'text', value: 'Trend ' },
      { type: 'hashtag', value: '#klimakrise' },
      { type: 'text', value: ' heute.' },
    ])
  })

  it('erkennt mehrere Marker hintereinander', () => {
    const tokens = tokenizeFeedText('@alex schreibt über #ki und #ml.')
    expect(tokens).toEqual([
      { type: 'mention', value: '@alex' },
      { type: 'text', value: ' schreibt über ' },
      { type: 'hashtag', value: '#ki' },
      { type: 'text', value: ' und ' },
      { type: 'hashtag', value: '#ml' },
      { type: 'text', value: '.' },
    ])
  })

  it('verträgt Unicode (Umlaute) im Hashtag', () => {
    expect(tokenizeFeedText('Wir reden über #übermorgen.')).toEqual([
      { type: 'text', value: 'Wir reden über ' },
      { type: 'hashtag', value: '#übermorgen' },
      { type: 'text', value: '.' },
    ])
  })

  it('matched keine Mention innerhalb einer E-Mail-Adresse', () => {
    // Word-Boundary vorn: vor `@` ist hier ein Word-Char, also kein Match.
    expect(tokenizeFeedText('Schreib an user@host.com.')).toEqual([
      { type: 'text', value: 'Schreib an user@host.com.' },
    ])
  })

  it('schliesst Satzpunkt am Ende nicht in die Mention ein', () => {
    expect(tokenizeFeedText('Frag mal @alex.')).toEqual([
      { type: 'text', value: 'Frag mal ' },
      { type: 'mention', value: '@alex' },
      { type: 'text', value: '.' },
    ])
  })
})
