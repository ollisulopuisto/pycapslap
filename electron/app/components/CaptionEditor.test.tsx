import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CaptionEditor } from './CaptionEditor'

const mockSettings = {
  selectedTemplate: 'oneliner' as const,
  exportFormats: ['9:16'],
  selectedFont: 'Montserrat Black',
  textColor: '#ffffff',
  highlightWordColor: '#ffff00',
  outlineColor: '#000000',
  glowEffect: false,
  captionStyle: 'oneliner' as const,
  captionPosition: 'bottom' as const,
  fontSize: 65,
}

const mockSegments = [
  {
    startMs: 0,
    endMs: 2000,
    text: 'Hello world',
    words: [
      { startMs: 0, endMs: 1000, text: 'Hello' },
      { startMs: 1000, endMs: 2000, text: 'world' },
    ],
  },
]

describe('CaptionEditor', () => {
  it('renders loading indicator when isLoadingPreview is true and previewFrame is null', () => {
    render(
      <CaptionEditor
        initialSegments={mockSegments}
        onBurn={vi.fn()}
        onCancel={vi.fn()}
        videoPath="test.mp4"
        settings={mockSettings}
        fontName="Montserrat Black"
        positionOverrides={[]}
        onPositionOverridesChange={vi.fn()}
        shownPlatforms={[]}
        onShownPlatformsChange={vi.fn()}
        previewFrame={null}
        isLoadingPreview={true}
      />
    )

    expect(screen.getByText('Loading preview frame…')).toBeInTheDocument()
  })

  it('renders preview frame image when previewFrame is provided', () => {
    const testImage = 'data:image/png;base64,mockframe'
    render(
      <CaptionEditor
        initialSegments={mockSegments}
        onBurn={vi.fn()}
        onCancel={vi.fn()}
        videoPath="test.mp4"
        settings={mockSettings}
        fontName="Montserrat Black"
        positionOverrides={[]}
        onPositionOverridesChange={vi.fn()}
        shownPlatforms={[]}
        onShownPlatformsChange={vi.fn()}
        previewFrame={testImage}
        isLoadingPreview={false}
      />
    )

    const img = screen.getByAltText('Preview')
    expect(img).toBeInTheDocument()
    expect(img).toHaveAttribute('src', testImage)
  })
})
