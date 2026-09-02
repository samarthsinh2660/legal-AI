"use client";

/**
 * The force simulation and the canvas that draws it.
 *
 * Canvas rather than SVG: 120 nodes is 120 DOM elements re-laid-out on
 * every one of the simulation's ~300 ticks, and the pan stutters. Canvas
 * redraws the whole scene in one pass.
 *
 * Colours are read from the CSS custom properties at mount rather than
 * written here, so the token pipeline in globals.css stays the only place
 * a value is defined -- a canvas cannot use a Tailwind class, but it can
 * read the variable behind one.
 */

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { drag as d3drag } from "d3-drag";
import { select } from "d3-selection";
import { zoom as d3zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { useCallback, useEffect, useRef, useState } from "react";

import type { GraphEdge, GraphNode } from "../types";

type SimNode = GraphNode & SimulationNodeDatum & { degree: number };
type SimLink = SimulationLinkDatum<SimNode> & { kind: string };

function token(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

/** Node colour by kind. Statutes take the STATIC KNOWLEDGE green and
 *  judgments the accent, which is the same distinction the provenance
 *  badges make everywhere else in the product. */
function palette() {
  return {
    Judgment: token("--primary", "#2563eb"),
    Section: token("--prov-static", "#1b5e3f"),
    Act: token("--prov-static", "#1b5e3f"),
    Court: token("--ink-muted", "#737686"),
    fallback: token("--ink-muted", "#737686"),
    line: token("--line-strong", "#c3c6d7"),
    ink: token("--ink", "#1a1c1c"),
    inkMuted: token("--ink-muted", "#737686"),
    card: token("--surface-card", "#ffffff"),
  };
}

export function useForceGraph(nodes: GraphNode[], edges: GraphEdge[]) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const transformRef = useRef<ZoomTransform>(zoomIdentity);
  const hoveredRef = useRef<string | null>(null);

  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  // Held so `resetView` can replay a transform through the same behaviour
  // the canvas is bound to -- a fresh one would reset the picture while
  // leaving d3's internal transform where it was, and the next scroll
  // would jump back.
  const zoomRef = useRef<ReturnType<
    typeof d3zoom<HTMLCanvasElement, unknown>
  > | null>(null);

  const resetView = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !zoomRef.current) return;
    select<HTMLCanvasElement, unknown>(canvas).call(
      zoomRef.current.transform,
      zoomIdentity,
    );
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap || nodes.length === 0) return;

    const context = canvas.getContext("2d");
    if (!context) return;
    const colours = palette();

    // Degree decides radius: the thing everything points at should look
    // like it.
    const degree = new Map<string, number>();
    for (const edge of edges) {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    }

    const simNodes: SimNode[] = nodes.map((node) => ({
      ...node,
      degree: degree.get(node.id) ?? 0,
    }));
    const byId = new Map(simNodes.map((node) => [node.id, node]));
    const simLinks: SimLink[] = edges
      .filter((edge) => byId.has(edge.source) && byId.has(edge.target))
      .map((edge) => ({
        source: byId.get(edge.source)!,
        target: byId.get(edge.target)!,
        kind: edge.kind,
      }));

    const radius = (node: SimNode) =>
      node.hops === 0 ? 11 : 5 + Math.min(node.degree, 8);

    const neighbours = new Map<string, Set<string>>();
    for (const link of simLinks) {
      const a = (link.source as SimNode).id;
      const b = (link.target as SimNode).id;
      if (!neighbours.has(a)) neighbours.set(a, new Set());
      if (!neighbours.has(b)) neighbours.set(b, new Set());
      neighbours.get(a)!.add(b);
      neighbours.get(b)!.add(a);
    }

    let width = wrap.clientWidth;
    let height = wrap.clientHeight;

    const resize = () => {
      width = wrap.clientWidth;
      height = wrap.clientHeight;
      // Back the canvas at device resolution or the text is soft.
      const ratio = window.devicePixelRatio || 1;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    resize();

    const simulation = forceSimulation<SimNode, SimLink>(simNodes)
      .force("link", forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(90).strength(0.5))
      .force("charge", forceManyBody().strength(-320))
      .force("center", forceCenter(width / 2, height / 2))
      // Stops labels sitting on top of each other.
      .force("collide", forceCollide<SimNode>((d) => radius(d) + 14));
    simRef.current = simulation;

    const draw = () => {
      const t = transformRef.current;
      context.save();
      context.clearRect(0, 0, width, height);
      context.translate(t.x, t.y);
      context.scale(t.k, t.k);

      const active = hoveredRef.current;
      const lit = active ? neighbours.get(active) ?? new Set<string>() : null;
      const isLit = (id: string) => !active || id === active || lit!.has(id);

      for (const link of simLinks) {
        const source = link.source as SimNode;
        const target = link.target as SimNode;
        const on = isLit(source.id) && isLit(target.id);
        context.beginPath();
        context.moveTo(source.x ?? 0, source.y ?? 0);
        context.lineTo(target.x ?? 0, target.y ?? 0);
        context.strokeStyle = colours.line;
        context.globalAlpha = on ? (link.kind === "CITES" ? 0.75 : 0.35) : 0.07;
        context.lineWidth = link.kind === "CITES" ? 1.4 : 1;
        context.stroke();
      }
      context.globalAlpha = 1;

      for (const node of simNodes) {
        const on = isLit(node.id);
        const r = radius(node);
        context.globalAlpha = on ? 1 : 0.12;

        context.beginPath();
        context.arc(node.x ?? 0, node.y ?? 0, r, 0, Math.PI * 2);
        context.fillStyle =
          (colours as Record<string, string>)[node.kind] ?? colours.fallback;
        context.fill();

        // The anchor wears a ring: in a field of dots, the one the reader
        // asked about must be findable without reading a label.
        if (node.hops === 0) {
          context.lineWidth = 3;
          context.strokeStyle = colours.card;
          context.stroke();
        }

        // Labels only where they can be read: close in, or on the node
        // under the cursor and its neighbours.
        const showLabel = t.k > 0.85 || (active !== null && on);
        if (showLabel && node.title) {
          const label =
            node.title.length > 34
              ? `${node.title.slice(0, 33)}…`
              : node.title;
          context.font = `${node.hops === 0 ? 600 : 400} 11px ui-sans-serif, system-ui, sans-serif`;
          context.textAlign = "center";
          context.fillStyle = node.hops === 0 ? colours.ink : colours.inkMuted;
          context.globalAlpha = on ? 1 : 0.1;
          context.fillText(label, node.x ?? 0, (node.y ?? 0) + r + 13);
        }
      }

      context.globalAlpha = 1;
      context.restore();
    };

    simulation.on("tick", draw);

    const at = (event: { clientX: number; clientY: number }) => {
      const box = canvas.getBoundingClientRect();
      const t = transformRef.current;
      const x = (event.clientX - box.left - t.x) / t.k;
      const y = (event.clientY - box.top - t.y) / t.k;
      return simNodes.find((node) => {
        const dx = (node.x ?? 0) - x;
        const dy = (node.y ?? 0) - y;
        return Math.hypot(dx, dy) < radius(node) + 5;
      });
    };

    const selection = select<HTMLCanvasElement, unknown>(canvas);

    const zoomBehaviour = d3zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.25, 4])
      .on("zoom", (event) => {
        transformRef.current = event.transform;
        draw();
      });
    zoomRef.current = zoomBehaviour;
    selection.call(zoomBehaviour);

    selection.call(
      d3drag<HTMLCanvasElement, unknown>()
        .subject((event) => at(event.sourceEvent))
        .on("start", (event) => {
          if (!event.subject) return;
          if (!event.active) simulation.alphaTarget(0.25).restart();
          event.subject.fx = event.subject.x;
          event.subject.fy = event.subject.y;
        })
        .on("drag", (event) => {
          if (!event.subject) return;
          const t = transformRef.current;
          const box = canvas.getBoundingClientRect();
          event.subject.fx =
            (event.sourceEvent.clientX - box.left - t.x) / t.k;
          event.subject.fy = (event.sourceEvent.clientY - box.top - t.y) / t.k;
        })
        .on("end", (event) => {
          if (!event.subject) return;
          if (!event.active) simulation.alphaTarget(0);
          // Released, not pinned: the layout should settle again.
          event.subject.fx = null;
          event.subject.fy = null;
        }),
    );

    const onMove = (event: MouseEvent) => {
      const found = at(event);
      const id = found?.id ?? null;
      if (id === hoveredRef.current) return;
      hoveredRef.current = id;
      canvas.style.cursor = id ? "pointer" : "grab";
      setHovered(found ?? null);
      draw();
    };
    const onClick = (event: MouseEvent) => setSelected(at(event) ?? null);

    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("click", onClick);

    const observer = new ResizeObserver(() => {
      resize();
      simulation.force("center", forceCenter(width / 2, height / 2));
      simulation.alpha(0.3).restart();
    });
    observer.observe(wrap);

    return () => {
      observer.disconnect();
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("click", onClick);
      selection.on(".zoom", null).on(".drag", null);
      simulation.stop();
    };
  }, [nodes, edges]);

  return { canvasRef, wrapRef, hovered, selected, setSelected, resetView };
}
