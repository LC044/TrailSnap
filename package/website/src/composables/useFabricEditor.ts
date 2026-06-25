import { ref, shallowRef } from 'vue'
import {
  Canvas,
  FabricImage,
  Textbox,
  Rect,
  Ellipse,
  Line,
  PencilBrush,
} from 'fabric'
import type { EditorTool } from '@/types/editor'
import { useEditorHistory } from './useEditorHistory'

const MAX_CANVAS_DIM = 4096

export function useFabricEditor() {
  const canvas = shallowRef<Canvas | null>(null)
  const activeTool = ref<EditorTool>('select')
  const drawColor = ref('#ff0000')
  const fillColor = ref('#ff000033')
  const strokeWidth = ref(3)
  const fontSize = ref(24)
  const isCropping = ref(false)
  const isReady = ref(false)
  const imageScale = ref(1)

  const history = useEditorHistory()
  const { canUndo, canRedo } = history

  let isRestoringState = false
  let shapeStartX = 0
  let shapeStartY = 0
  let activeShape: Rect | Ellipse | Line | null = null
  let cropRect: Rect | null = null
  let cropOverlay: Rect | null = null
  let originalImageSrc = ''
  let originalWidth = 0
  let originalHeight = 0

  function initCanvas(canvasEl: HTMLCanvasElement, imageEl: HTMLImageElement) {
    originalImageSrc = imageEl.src
    originalWidth = imageEl.naturalWidth || imageEl.width
    originalHeight = imageEl.naturalHeight || imageEl.height

    // canvasEl is inside canvasContainer; Fabric will replace canvasEl with its wrapper
    const container = canvasEl.parentElement!
    let containerW = container.clientWidth
    let containerH = container.clientHeight

    // Fallback if container hasn't laid out yet
    if (containerW === 0 || containerH === 0) {
      containerW = window.innerWidth
      containerH = window.innerHeight * 0.7
    }

    // Leave some padding so the canvas doesn't touch edges
    containerW -= 32
    containerH -= 32

    // Fit image into container maintaining aspect ratio
    const imgAspect = originalWidth / originalHeight
    const containerAspect = containerW / containerH
    let canvasW: number, canvasH: number
    if (imgAspect > containerAspect) {
      canvasW = Math.min(originalWidth, containerW, MAX_CANVAS_DIM)
      canvasH = canvasW / imgAspect
    } else {
      canvasH = Math.min(originalHeight, containerH, MAX_CANVAS_DIM)
      canvasW = canvasH * imgAspect
    }

    const fabricCanvas = new Canvas(canvasEl, {
      width: canvasW,
      height: canvasH,
      backgroundColor: '',
      selection: true,
    })

    // Center the Fabric.js wrapper div within the flex container
    // Fabric replaces the <canvas> with: div[data-fabric="wrapper"] > canvas + canvas
    const fabricWrapper = canvasEl.closest('[data-fabric="wrapper"]') as HTMLElement
      || canvasEl.parentElement as HTMLElement
    if (fabricWrapper) {
      fabricWrapper.style.margin = 'auto'
    }

    imageScale.value = canvasW / originalWidth

    const scale = canvasW / originalWidth
    const fImg = new FabricImage(imageEl, {
      left: canvasW / 2,
      top: canvasH / 2,
      originX: 'center',
      originY: 'center',
      scaleX: scale,
      scaleY: scale,
      selectable: false,
      evented: false,
      objectCaching: false,
    })
    fabricCanvas.add(fImg)
    fabricCanvas.sendObjectToBack(fImg)
    fabricCanvas.renderAll()

    fabricCanvas.on('object:modified', () => {
      if (!isRestoringState) pushHistoryState()
    })
    fabricCanvas.on('path:created', () => {
      if (!isRestoringState) pushHistoryState()
    })

    canvas.value = fabricCanvas
    isReady.value = true
    pushHistoryState()
  }

  function pushHistoryState() {
    if (!canvas.value) return
    history.pushState(JSON.stringify(canvas.value.toJSON()))
  }

  function applyTool(tool: EditorTool) {
    if (!canvas.value) return
    const c = canvas.value
    activeTool.value = tool

    // Reset modes
    c.isDrawingMode = false
    c.selection = false
    c.forEachObject((obj) => {
      if (obj instanceof FabricImage && c.getObjects().indexOf(obj) === 0) return
      obj.selectable = false
      obj.evented = false
    })

    switch (tool) {
      case 'select':
        c.selection = true
        c.forEachObject((obj) => {
          if (obj instanceof FabricImage && c.getObjects().indexOf(obj) === 0) return
          obj.selectable = true
          obj.evented = true
        })
        break
      case 'draw':
        c.isDrawingMode = true
        c.freeDrawingBrush = new PencilBrush(c)
        c.freeDrawingBrush.color = drawColor.value
        c.freeDrawingBrush.width = strokeWidth.value
        break
      case 'text':
        c.selection = true
        break
      case 'rect':
      case 'ellipse':
      case 'line':
        c.selection = false
        break
    }
    c.discardActiveObject()
    c.renderAll()
  }

  function handleCanvasMouseDown(opt: any) {
    if (!canvas.value || isCropping.value) return
    const c = canvas.value
    const pointer = c.getScenePoint(opt.e)

    if (activeTool.value === 'text') {
      const text = new Textbox('文字', {
        left: pointer.x,
        top: pointer.y,
        fontSize: fontSize.value,
        fill: drawColor.value,
        fontFamily: 'sans-serif',
      })
      c.add(text)
      c.setActiveObject(text)
      c.renderAll()
      pushHistoryState()
      applyTool('select')
      return
    }

    if (activeTool.value === 'rect' || activeTool.value === 'ellipse' || activeTool.value === 'line') {
      shapeStartX = pointer.x
      shapeStartY = pointer.y

      if (activeTool.value === 'rect') {
        activeShape = new Rect({
          left: pointer.x,
          top: pointer.y,
          width: 1,
          height: 1,
          originX: 'left',
          originY: 'top',
          fill: 'transparent',
          stroke: drawColor.value,
          strokeWidth: strokeWidth.value,
        })
        c.add(activeShape)
      } else if (activeTool.value === 'ellipse') {
        activeShape = new Ellipse({
          left: pointer.x,
          top: pointer.y,
          rx: 0.5,
          ry: 0.5,
          originX: 'left',
          originY: 'top',
          fill: 'transparent',
          stroke: drawColor.value,
          strokeWidth: strokeWidth.value,
        })
        c.add(activeShape)
      } else if (activeTool.value === 'line') {
        activeShape = new Line([pointer.x, pointer.y, pointer.x, pointer.y], {
          stroke: drawColor.value,
          strokeWidth: strokeWidth.value,
        })
        c.add(activeShape)
      }
    }
  }

  function handleCanvasMouseMove(opt: any) {
    if (!canvas.value || !activeShape) return
    const c = canvas.value
    const pointer = c.getScenePoint(opt.e)

    if (activeShape instanceof Rect) {
      const left = Math.min(shapeStartX, pointer.x)
      const top = Math.min(shapeStartY, pointer.y)
      const w = Math.abs(pointer.x - shapeStartX)
      const h = Math.abs(pointer.y - shapeStartY)
      activeShape.set({ left, top, width: w, height: h })
    } else if (activeShape instanceof Ellipse) {
      const left = Math.min(shapeStartX, pointer.x)
      const top = Math.min(shapeStartY, pointer.y)
      const w = Math.abs(pointer.x - shapeStartX)
      const h = Math.abs(pointer.y - shapeStartY)
      activeShape.set({ left, top, rx: w / 2, ry: h / 2 })
    } else if (activeShape instanceof Line) {
      activeShape.set({ x2: pointer.x, y2: pointer.y })
    }
    c.renderAll()
  }

  function handleCanvasMouseUp() {
    if (activeShape) {
      activeShape.setCoords()
      pushHistoryState()
      activeShape = null
    }
  }

  function setDrawColor(color: string) {
    drawColor.value = color
    if (canvas.value?.isDrawingMode && canvas.value.freeDrawingBrush) {
      canvas.value.freeDrawingBrush.color = color
    }
  }

  function setStrokeWidth(width: number) {
    strokeWidth.value = width
    if (canvas.value?.isDrawingMode && canvas.value.freeDrawingBrush) {
      canvas.value.freeDrawingBrush.width = width
    }
  }

  function setFontSize(size: number) {
    fontSize.value = size
  }

  function rotate(degrees: number = 90) {
    if (!canvas.value) return
    const c = canvas.value
    const bgImg = c.getObjects()[0]
    if (!bgImg) return
    const currentAngle = bgImg.angle || 0
    const newAngle = currentAngle + degrees

    // Swap canvas dimensions for 90/270 degree rotations
    const newW = (newAngle % 180 !== 0) ? c.getHeight() : c.getWidth()
    const newH = (newAngle % 180 !== 0) ? c.getWidth() : c.getHeight()

    c.setDimensions({ width: newW, height: newH })

    bgImg.set({
      angle: newAngle,
      originX: 'center',
      originY: 'center',
      left: newW / 2,
      top: newH / 2,
      scaleX: imageScale.value,
      scaleY: imageScale.value,
    })

    c.renderAll()
    pushHistoryState()
  }

  function _addCropUI(cw: number, ch: number, cropL: number, cropT: number, cropW: number, cropH: number) {
    const c = canvas.value!
    // Remove old crop objects if any
    if (cropRect) c.remove(cropRect)
    if (cropOverlay) c.remove(cropOverlay)

    // Dark overlay — covers entire canvas
    cropOverlay = new Rect({
      left: 0,
      top: 0,
      width: cw,
      height: ch,
      originX: 'left',
      originY: 'top',
      fill: 'rgba(0,0,0,0.5)',
      selectable: false,
      evented: false,
    })
    c.add(cropOverlay)

    // Crop selection rectangle
    cropRect = new Rect({
      left: cropL,
      top: cropT,
      width: cropW,
      height: cropH,
      originX: 'left',
      originY: 'top',
      fill: 'transparent',
      stroke: '#ffffff',
      strokeWidth: 2,
      strokeDashArray: [8, 4],
      hasRotatingPoint: false,
      transparentCorners: false,
      cornerColor: '#ffffff',
      cornerSize: 10,
      borderScaleFactor: 1.5,
    })
    c.add(cropRect)
    c.setActiveObject(cropRect)
    c.renderAll()
  }

  function startCrop() {
    if (!canvas.value) return
    isCropping.value = true
    const c = canvas.value

    // Switch to select mode and disable drawing so mouse events only control the crop rect
    c.isDrawingMode = false
    activeTool.value = 'crop'

    const w = c.width!
    const h = c.height!
    const margin = Math.min(w, h) * 0.15

    _addCropUI(w, h, margin, margin, w - margin * 2, h - margin * 2)
  }

  /**
   * Adjust the crop rectangle to a specific aspect ratio.
   * ratio: number (width/height) or null for free form
   */
  function setCropRatio(ratio: number | null) {
    if (!canvas.value || !cropRect) return
    const c = canvas.value
    const cw = c.width!
    const ch = c.height!

    if (ratio === null) {
      // Free form — just keep current selection, reset lock
      cropRect.set({ lockUniScaling: false })
      c.setActiveObject(cropRect)
      c.renderAll()
      return
    }

    // Calculate largest rect with given ratio that fits inside canvas with 15% margin
    const margin = Math.min(cw, ch) * 0.15
    const maxW = cw - margin * 2
    const maxH = ch - margin * 2

    let cropW: number, cropH: number
    if (maxW / maxH > ratio) {
      // Height-limited
      cropH = maxH
      cropW = cropH * ratio
    } else {
      // Width-limited
      cropW = maxW
      cropH = cropW / ratio
    }

    const cropL = (cw - cropW) / 2
    const cropT = (ch - cropH) / 2

    // Lock aspect ratio during resize
    cropRect.set({ lockUniScaling: true })
    _addCropUI(cw, ch, cropL, cropT, cropW, cropH)
  }

  function applyCrop() {
    if (!canvas.value || !cropRect) return
    const c = canvas.value

    // Use getBoundingRect() to get the true pixel bounding box
    const bounds = cropRect.getBoundingRect()
    const cropLeft = Math.max(0, Math.round(bounds.left))
    const cropTop = Math.max(0, Math.round(bounds.top))
    const cropRight = Math.min(c.width!, Math.round(bounds.left + bounds.width))
    const cropBottom = Math.min(c.height!, Math.round(bounds.top + bounds.height))
    const cropWidth = Math.max(1, cropRight - cropLeft)
    const cropHeight = Math.max(1, cropBottom - cropTop)

    // Remove crop UI objects before export
    c.remove(cropRect)
    if (cropOverlay) c.remove(cropOverlay)
    c.discardActiveObject()

    // Temporarily remove background color so cropped image has no black fill
    const prevBg = c.backgroundColor
    c.backgroundColor = ''
    c.renderAll()

    // Export at original resolution using the same multiplier as exportToBlob
    const multiplier = 1 / imageScale.value
    const dataUrl = c.toDataURL({
      format: 'png',
      left: cropLeft,
      top: cropTop,
      width: cropWidth,
      height: cropHeight,
      multiplier,
    })

    // Restore background
    c.backgroundColor = prevBg

    // The exported image is at original resolution: cropWidth * multiplier × cropHeight * multiplier
    const fullResW = cropWidth * multiplier
    const fullResH = cropHeight * multiplier

    // Load the cropped image and rebuild the canvas
    const imgEl = new Image()
    imgEl.onload = () => {
      c.clear()
      c.backgroundColor = ''
      c.setDimensions({ width: cropWidth, height: cropHeight })

      // Scale the full-res image to fit the canvas display size
      const newScale = cropWidth / imgEl.naturalWidth
      const fImg = new FabricImage(imgEl, {
        left: cropWidth / 2,
        top: cropHeight / 2,
        originX: 'center',
        originY: 'center',
        scaleX: newScale,
        scaleY: newScale,
        selectable: false,
        evented: false,
        objectCaching: false,
      })
      c.add(fImg)
      c.sendObjectToBack(fImg)
      c.renderAll()

      imageScale.value = newScale
      originalWidth = imgEl.naturalWidth
      originalHeight = imgEl.naturalHeight

      cropRect = null
      cropOverlay = null
      isCropping.value = false
      activeTool.value = 'select'
      c.selection = true
      pushHistoryState()
    }
    imgEl.src = dataUrl
  }

  function cancelCrop() {
    if (!canvas.value) return
    if (cropRect) canvas.value.remove(cropRect)
    if (cropOverlay) canvas.value.remove(cropOverlay)
    cropRect = null
    cropOverlay = null
    isCropping.value = false
    activeTool.value = 'select'
    canvas.value.discardActiveObject()
    canvas.value.renderAll()
  }

  function undo() {
    if (!canvas.value) return
    const json = history.undo()
    if (!json) return
    isRestoringState = true
    canvas.value.loadFromJSON(JSON.parse(json)).then(() => {
      canvas.value!.renderAll()
      isRestoringState = false
    })
  }

  function redo() {
    if (!canvas.value) return
    const json = history.redo()
    if (!json) return
    isRestoringState = true
    canvas.value.loadFromJSON(JSON.parse(json)).then(() => {
      canvas.value!.renderAll()
      isRestoringState = false
    })
  }

  async function exportToBlob(
    format: 'jpeg' | 'png' | 'webp' = 'jpeg',
    quality = 0.92,
  ): Promise<Blob> {
    if (!canvas.value) throw new Error('Canvas not initialized')
    const c = canvas.value
    // Deselect all objects so selection handles are not exported
    c.discardActiveObject()
    c.renderAll()

    const multiplier = 1 / imageScale.value
    const dataUrl = c.toDataURL({
      format,
      quality,
      multiplier,
    })
    const res = await fetch(dataUrl)
    return res.blob()
  }

  function deleteSelected() {
    if (!canvas.value) return
    const active = canvas.value.getActiveObjects()
    // Don't delete the background image (first object)
    const bgImg = canvas.value.getObjects()[0]
    active.forEach((obj) => {
      if (obj !== bgImg) canvas.value!.remove(obj)
    })
    canvas.value.discardActiveObject()
    canvas.value.renderAll()
    pushHistoryState()
  }

  function dispose() {
    if (canvas.value) {
      canvas.value.dispose()
      canvas.value = null
    }
    isReady.value = false
    isCropping.value = false
    history.reset()
  }

  return {
    canvas,
    activeTool,
    drawColor,
    fillColor,
    strokeWidth,
    fontSize,
    isCropping,
    isReady,
    canUndo,
    canRedo,
    initCanvas,
    applyTool,
    handleCanvasMouseDown,
    handleCanvasMouseMove,
    handleCanvasMouseUp,
    setDrawColor,
    setStrokeWidth,
    setFontSize,
    rotate,
    startCrop,
    setCropRatio,
    applyCrop,
    cancelCrop,
    undo,
    redo,
    exportToBlob,
    deleteSelected,
    dispose,
  }
}
