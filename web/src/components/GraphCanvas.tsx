import cytoscape, { type Core, type NodeSingular } from 'cytoscape'
import type { FcoseLayoutOptions } from 'cytoscape-fcose'
import fcose from 'cytoscape-fcose'
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { edgeElement, nodeElement } from '../graph/elements'
import { stylesheet } from '../graph/style'
import { ContextMenu, type MenuState } from './ContextMenu'

cytoscape.use(fcose)

const LAYOUT: FcoseLayoutOptions = {
  name: 'fcose',
  animate: true,
  animationDuration: 500,
  randomize: false,
  fit: false,
  nodeRepulsion: () => 6000,
  idealEdgeLength: () => 70,
  gravity: 0.25,
  numIter: 1500,
  padding: 40,
}

export function GraphCanvas() {
  const ref = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  const [menu, setMenu] = useState<MenuState | null>(null)

  const nodes = useStore((s) => s.nodes)
  const edges = useStore((s) => s.edges)
  const selected = useStore((s) => s.selected)
  const highlight = useStore((s) => s.highlight)
  const filters = useStore((s) => s.filters)
  const pathFrom = useStore((s) => s.pathFrom)
  const pathTo = useStore((s) => s.pathTo)
  const layoutTick = useStore((s) => s.layoutTick)

  // Create the Cytoscape instance once.
  useEffect(() => {
    if (!ref.current) return
    const cy = cytoscape({ container: ref.current, style: stylesheet, wheelSensitivity: 0.2, minZoom: 0.05, maxZoom: 4 })
    cyRef.current = cy
    const { select, loadNeighbors } = useStore.getState()

    cy.on('tap', 'node', (ev) => select((ev.target as NodeSingular).id()))
    cy.on('tap', (ev) => {
      if (ev.target === cy) {
        select(null)
        setMenu(null)
      }
    })
    cy.on('dbltap', 'node', (ev) => void loadNeighbors((ev.target as NodeSingular).id()))
    cy.on('cxttap', 'node', (ev) => {
      const n = ev.target as NodeSingular
      const pos = ev.renderedPosition
      setMenu({ id: n.id(), label: n.data('label'), x: pos.x, y: pos.y })
    })
    cy.on('pan zoom drag', () => setMenu(null))
    return () => cy.destroy()
  }, [])

  // Sync store elements -> cytoscape (incremental add/remove) and run layout for additions.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    const wanted = new Set([...Object.keys(nodes), ...Object.keys(edges)])
    const toRemove = cy.elements().filter((el) => !wanted.has(el.id()))
    const newNodes = Object.values(nodes).filter((n) => cy.getElementById(n.id).empty()).map(nodeElement)
    const newEdges = Object.values(edges).filter((e) => cy.getElementById(e.id).empty()).map(edgeElement)

    cy.batch(() => {
      toRemove.remove()
      // Update data for existing nodes (e.g. a stub that has now been fetched).
      for (const n of Object.values(nodes)) {
        const el = cy.getElementById(n.id)
        if (el.nonempty()) el.data(nodeElement(n).data)
      }
      const added = cy.add([...newNodes, ...newEdges])
      // Place new nodes near a connected existing node so the layout starts sensibly.
      added.nodes().forEach((n) => {
        const anchor = n.connectedEdges().connectedNodes().filter((m) => m.id() !== n.id() && !added.contains(m)).first() as NodeSingular
        const base = anchor.nonempty() ? anchor.position() : { x: cy.width() / 2, y: cy.height() / 2 }
        n.position({ x: base.x + (Math.random() - 0.5) * 80, y: base.y + (Math.random() - 0.5) * 80 })
      })
    })
    if (newNodes.length > 0) {
      const firstLoad = cy.nodes().length === newNodes.length
      const layout = cy.layout({ ...LAYOUT, fit: firstLoad } as FcoseLayoutOptions)
      layout.run()
      if (!firstLoad) layout.on('layoutstop', () => cy.animate({ fit: { eles: cy.elements(), padding: 40 }, duration: 300 }))
    }
  }, [nodes, edges])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy || cy.nodes().length === 0) return
    cy.layout({ ...LAYOUT, randomize: true, fit: true } as FcoseLayoutOptions).run()
  }, [layoutTick])

  // Selection sync.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements(':selected').unselect()
    if (selected) cy.getElementById(selected).select()
  }, [selected])

  // Path endpoints.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().removeClass('pathFrom pathTo')
    if (pathFrom) cy.getElementById(pathFrom).addClass('pathFrom')
    if (pathTo) cy.getElementById(pathTo).addClass('pathTo')
  }, [pathFrom, pathTo, nodes])

  // Path highlight.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.elements().removeClass('path faded')
      if (highlight.size === 0) return
      cy.elements().forEach((el) => {
        el.addClass(highlight.has(el.id()) ? 'path' : 'faded')
      })
    })
  }, [highlight, nodes, edges])

  // Visibility filters.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        n.toggleClass('hidden', !filters.labels[n.data('label') as keyof typeof filters.labels])
      })
      cy.edges().forEach((e) => {
        const type = e.data('type') as keyof typeof filters.rels
        const langOk = type !== 'VOICES' || !filters.lang || e.data('language') === filters.lang
        e.toggleClass('hidden', !filters.rels[type] || !langOk)
      })
    })
  }, [filters, nodes, edges])

  return (
    <div className="canvas-wrap">
      <div ref={ref} className="canvas" />
      {menu && <ContextMenu menu={menu} onClose={() => setMenu(null)} />}
      {Object.keys(nodes).length === 0 && (
        <div className="empty-hint">
          Search for an anime, character or voice actor to start.
          <br />
          <small>click = select · double-click = expand neighbours · right-click = more</small>
        </div>
      )}
    </div>
  )
}
