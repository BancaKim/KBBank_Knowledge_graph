import { useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from "react";
import * as d3 from "d3";
import type { GraphNode, GraphLink, GraphData } from "../types/graph";
import { NODE_COLORS } from "../types/graph";

export interface GraphCanvasRef {
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
}

interface Props {
  data: GraphData;
  onNodeClick: (node: GraphNode) => void;
  highlightNodeId?: string | null;
  highlightNodeIds?: string[];
  selectedCategories: Set<string>;
  selectedNodeTypes: Set<string>;
}

/** Edge colors by relationship type (Neo4j style) */
const EDGE_COLORS: Record<string, string> = {
  BELONGS_TO: "#F5A623",
  HAS_SUBCATEGORY: "#E65100",
  HAS_FEATURE: "#7ED321",
  HAS_RATE: "#D0021B",
  HAS_TERM: "#9B59B6",
  AVAILABLE_VIA: "#1ABC9C",
  REQUIRES: "#95A5A6",
  REPAID_VIA: "#E67E22",
  HAS_TAX_BENEFIT: "#27AE60",
  PROTECTED_BY: "#2980B9",
  HAS_PREFERENTIAL_RATE: "#E74C3C",
  HAS_FEE: "#8E44AD",
  HAS_TYPE: "#16A085",
};

/** Stored D3 state for highlight updates without re-creating the graph */
interface D3State {
  node: d3.Selection<SVGCircleElement, GraphNode, SVGGElement, unknown>;
  link: d3.Selection<SVGLineElement, GraphLink, SVGGElement, unknown>;
  label: d3.Selection<SVGTextElement, GraphNode, SVGGElement, unknown>;
  linkLabel: d3.Selection<SVGTextElement, GraphLink, SVGGElement, unknown>;
  connectedMap: Map<string, Set<string>>;
  nodes: GraphNode[];
}

const GraphCanvas = forwardRef<GraphCanvasRef, Props>(function GraphCanvas(
  { data, onNodeClick, highlightNodeId, highlightNodeIds = [], selectedCategories, selectedNodeTypes },
  ref
) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphLink>>(undefined);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown>>(undefined);
  const selectedNodeRef = useRef<string | null>(null);
  const d3StateRef = useRef<D3State | null>(null);

  useImperativeHandle(ref, () => ({
    zoomIn: () => {
      if (svgRef.current && zoomRef.current)
        d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.scaleBy, 1.3);
    },
    zoomOut: () => {
      if (svgRef.current && zoomRef.current)
        d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.scaleBy, 0.7);
    },
    resetZoom: () => {
      if (svgRef.current && zoomRef.current)
        d3.select(svgRef.current).transition().duration(500).call(zoomRef.current.transform, d3.zoomIdentity);
    },
  }));

  const getFilteredData = useCallback(() => {
    const visibleProductIds = new Set<string>();
    data.nodes.forEach((n) => {
      if (n.type === "product" && selectedNodeTypes.has("product")) {
        if (selectedCategories.size === 0 || selectedCategories.has(String(n.data.category || "")))
          visibleProductIds.add(n.id);
      }
    });
    const connectedToProduct = new Set<string>(visibleProductIds);
    data.links.forEach((l) => {
      const src = typeof l.source === "string" ? l.source : l.source.id;
      const tgt = typeof l.target === "string" ? l.target : l.target.id;
      if (visibleProductIds.has(src)) connectedToProduct.add(tgt);
      if (visibleProductIds.has(tgt)) connectedToProduct.add(src);
    });
    const nodes = data.nodes.filter((n) => {
      if (!selectedNodeTypes.has(n.type)) return false;
      if (n.type === "product") return visibleProductIds.has(n.id);
      if (n.type === "parentcategory") {
        const childCats = n.label === "예금"
          ? ["정기예금", "적금", "입출금통장", "청약"]
          : ["신용대출", "담보대출", "전월세대출", "자동차대출"];
        return selectedCategories.size === 0 || childCats.some((c) => selectedCategories.has(c));
      }
      if (n.type === "category") return selectedCategories.size === 0 || selectedCategories.has(n.label);
      return connectedToProduct.has(n.id);
    });
    const nodeIds = new Set(nodes.map((n) => n.id));
    const links = data.links.filter((l) => {
      const src = typeof l.source === "string" ? l.source : l.source.id;
      const tgt = typeof l.target === "string" ? l.target : l.target.id;
      return nodeIds.has(src) && nodeIds.has(tgt);
    });
    return { nodes, links };
  }, [data, selectedCategories, selectedNodeTypes]);

  // ========== MAIN EFFECT: Build the D3 graph ==========
  useEffect(() => {
    if (!svgRef.current || !data) return;

    const tooltip = tooltipRef.current;
    selectedNodeRef.current = null;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const container = svg.node()!.parentElement!;
    const width = container.clientWidth;
    const height = container.clientHeight;
    svg.attr("width", width).attr("height", height);

    const filtered = getFilteredData();
    const nodes = filtered.nodes.map((d) => ({ ...d }));
    const links = filtered.links.map((d) => ({ ...d }));

    // Connection count for sizing
    const connectionCount = new Map<string, number>();
    links.forEach((l) => {
      const src = typeof l.source === "string" ? l.source : l.source.id;
      const tgt = typeof l.target === "string" ? l.target : l.target.id;
      connectionCount.set(src, (connectionCount.get(src) || 0) + 1);
      connectionCount.set(tgt, (connectionCount.get(tgt) || 0) + 1);
    });

    // O(1) neighbor lookup
    const connectedMap = new Map<string, Set<string>>();
    const visibleLinks = links.filter((l) => l.type !== "COMPETES_WITH");
    visibleLinks.forEach((l) => {
      const src = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const tgt = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      if (!connectedMap.has(src)) connectedMap.set(src, new Set());
      if (!connectedMap.has(tgt)) connectedMap.set(tgt, new Set());
      connectedMap.get(src)!.add(tgt);
      connectedMap.get(tgt)!.add(src);
    });

    function isLinkOf(l: GraphLink, nodeId: string): boolean {
      const src = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const tgt = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      return src === nodeId || tgt === nodeId;
    }

    function radius(d: GraphNode): number {
      const c = connectionCount.get(d.id) || 1;
      if (d.type === "parentcategory") return 28;
      if (d.type === "category") return 18 + Math.min(c * 0.2, 8);
      if (d.type === "product") return 8 + Math.min(c * 0.5, 6);
      return 5 + Math.min(c * 0.3, 4);
    }

    // Minimal defs - just arrowhead, NO filters
    const defs = svg.append("defs");
    defs.append("marker").attr("id", "arrow").attr("viewBox", "0 -5 10 10")
      .attr("refX", 20).attr("refY", 0).attr("markerWidth", 5).attr("markerHeight", 5)
      .attr("orient", "auto").append("path").attr("d", "M0,-3L7,0L0,3").attr("fill", "#444");

    const g = svg.append("g");

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.1, 10])
      .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);
    zoomRef.current = zoom;

    // === LINKS ===
    const link = g.append("g").selectAll<SVGLineElement, GraphLink>("line").data(visibleLinks).join("line")
      .attr("stroke", "#333").attr("stroke-opacity", 0.2).attr("stroke-width", 0.7)
      .attr("marker-end", "url(#arrow)");

    // === LINK LABELS (hidden by default, shown on select) ===
    const linkLabel = g.append("g").selectAll<SVGTextElement, GraphLink>("text").data(visibleLinks).join("text")
      .text((d) => d.type.replace(/_/g, " "))
      .attr("font-size", 9).attr("fill", "#aaa").attr("text-anchor", "middle")
      .attr("dominant-baseline", "central").attr("pointer-events", "none")
      .attr("visibility", "hidden");

    // === NODES ===
    const node = g.append("g").selectAll<SVGCircleElement, GraphNode>("circle")
      .data(nodes).join("circle")
      .attr("r", radius)
      .attr("fill", (d) => NODE_COLORS[d.type] || "#999")
      .attr("stroke", "#ffffff30")
      .attr("stroke-width", 1)
      .attr("cursor", "pointer");

    // === LABELS ===
    const label = g.append("g").selectAll<SVGTextElement, GraphNode>("text").data(nodes).join("text")
      .text((d) => d.label.length > 14 ? d.label.slice(0, 14) + "\u2026" : d.label)
      .attr("font-size", (d) => d.type === "parentcategory" ? 13 : d.type === "category" ? 11 : d.type === "product" ? 8 : 7)
      .attr("font-weight", (d) => d.type === "parentcategory" || d.type === "category" ? "bold" : "normal")
      .attr("fill", "#ccc").attr("text-anchor", "middle")
      .attr("dy", (d) => radius(d) + 10).attr("pointer-events", "none");

    // Store D3 state in ref for highlight effect
    d3StateRef.current = { node, link, label, linkLabel, connectedMap, nodes };

    // ========== STATE: Neo4j style - instant, no animation ==========

    function resetAll() {
      node.attr("opacity", 1)
        .attr("stroke", "#ffffff30")
        .attr("stroke-width", 1);
      link.attr("stroke", "#333").attr("stroke-opacity", 0.2).attr("stroke-width", 0.7);
      label.attr("opacity", 0.7);
      linkLabel.attr("visibility", "hidden");
    }

    function highlight(nodeId: string) {
      const neighbors = connectedMap.get(nodeId) || new Set<string>();

      // Nodes: selected=bright ring, neighbors=visible, rest=faded
      node.attr("opacity", (d) => d.id === nodeId || neighbors.has(d.id) ? 1 : 0.08)
        .attr("stroke", (d) => {
          if (d.id === nodeId) return "#FFD700";
          if (neighbors.has(d.id)) return "#ffffff80";
          return "#ffffff10";
        })
        .attr("stroke-width", (d) => d.id === nodeId ? 4 : neighbors.has(d.id) ? 2 : 0.5);

      // Links: connected=colored+thick, rest=nearly invisible
      link.attr("stroke", (l) => isLinkOf(l, nodeId) ? (EDGE_COLORS[l.type] || "#888") : "#222")
        .attr("stroke-opacity", (l) => isLinkOf(l, nodeId) ? 0.9 : 0.03)
        .attr("stroke-width", (l) => isLinkOf(l, nodeId) ? 2.5 : 0.5);

      // Labels: only show for selected + neighbors
      label.attr("opacity", (d) => d.id === nodeId || neighbors.has(d.id) ? 1 : 0.04);

      // Edge labels: show for connected edges
      linkLabel.attr("visibility", (l) => isLinkOf(l, nodeId) ? "visible" : "hidden")
        .attr("fill", (l) => EDGE_COLORS[l.type] || "#aaa");
    }

    // ========== INTERACTIONS ==========

    node.on("mouseover", function (event, d) {
      if (!selectedNodeRef.current) highlight(d.id);
      if (tooltip) {
        tooltip.textContent = "";
        const strong = document.createElement("strong");
        strong.textContent = d.label;
        tooltip.appendChild(strong);
        tooltip.appendChild(document.createElement("br"));
        const span = document.createElement("span");
        span.style.color = NODE_COLORS[d.type] || "#999";
        span.textContent = d.type;
        tooltip.appendChild(span);
        if (d.data.rate_min != null) {
          tooltip.appendChild(document.createElement("br"));
          tooltip.appendChild(document.createTextNode(`금리: ${d.data.rate_min}%~${d.data.rate_max}%`));
        }
        tooltip.style.left = event.pageX + 12 + "px";
        tooltip.style.top = event.pageY - 8 + "px";
        tooltip.style.opacity = "1";
      }
    })
    .on("mousemove", (event) => {
      if (tooltip) { tooltip.style.left = event.pageX + 12 + "px"; tooltip.style.top = event.pageY - 8 + "px"; }
    })
    .on("mouseout", function () {
      if (!selectedNodeRef.current) resetAll();
      if (tooltip) tooltip.style.opacity = "0";
    })
    .on("click", (event, d) => {
      event.stopPropagation();
      if (selectedNodeRef.current === d.id) {
        selectedNodeRef.current = null;
        resetAll();
      } else {
        selectedNodeRef.current = d.id;
        highlight(d.id);
      }
      onNodeClick(d);
    });

    svg.on("click", (event) => {
      if (event.target === svgRef.current) {
        selectedNodeRef.current = null;
        resetAll();
      }
    });

    // Drag
    node.call(d3.drag<SVGCircleElement, GraphNode>()
      .on("start", (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end", (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );

    // ========== CLUSTERING SIMULATION ==========
    const categoryOf = new Map<string, string>();
    nodes.forEach((n) => { if (n.type === "product") categoryOf.set(n.id, String(n.data.category || "")); });
    links.forEach((l) => {
      const src = typeof l.source === "string" ? l.source : l.source.id;
      const tgt = typeof l.target === "string" ? l.target : l.target.id;
      if (categoryOf.has(src) && !categoryOf.has(tgt)) categoryOf.set(tgt, categoryOf.get(src)!);
      if (categoryOf.has(tgt) && !categoryOf.has(src)) categoryOf.set(src, categoryOf.get(tgt)!);
    });
    nodes.forEach((n) => {
      if (n.type === "category") categoryOf.set(n.id, n.label);
      if (n.type === "parentcategory") categoryOf.set(n.id, n.label);
    });

    const uniqueCats = [...new Set(categoryOf.values())].filter(Boolean);
    const clusterCenters = new Map<string, { x: number; y: number }>();
    const cr = Math.min(width, height) * 0.35;
    uniqueCats.forEach((cat, i) => {
      const a = (2 * Math.PI * i) / uniqueCats.length - Math.PI / 2;
      clusterCenters.set(cat, { x: width / 2 + cr * Math.cos(a), y: height / 2 + cr * Math.sin(a) });
    });

    const physicsLinks = links.filter((l) => l.type !== "COMPETES_WITH");

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force("link", d3.forceLink<GraphNode, GraphLink>(physicsLinks).id((d) => d.id)
        .distance((d) => d.type === "HAS_SUBCATEGORY" ? 180 : d.type === "BELONGS_TO" ? 100 : 70)
        .strength((d) => d.type === "BELONGS_TO" || d.type === "HAS_SUBCATEGORY" ? 0.7 : 0.2))
      .force("charge", d3.forceManyBody().strength((d) => {
        const t = (d as GraphNode).type;
        return t === "parentcategory" ? -600 : t === "category" ? -350 : t === "product" ? -150 : -60;
      }))
      .force("center", d3.forceCenter(width / 2, height / 2).strength(0.03))
      .force("collide", d3.forceCollide().radius((d) => {
        const t = (d as GraphNode).type;
        return t === "parentcategory" ? 40 : t === "category" ? 28 : t === "product" ? 20 : 12;
      }).strength(0.8))
      .force("cluster", (alpha: number) => {
        nodes.forEach((d) => {
          const cat = categoryOf.get(d.id);
          if (!cat) return;
          const c = clusterCenters.get(cat);
          if (!c) return;
          const s = d.type === "parentcategory" ? 0.6 : d.type === "category" ? 0.5 : 0.15;
          d.vx = (d.vx || 0) + (c.x - (d.x || 0)) * s * alpha;
          d.vy = (d.vy || 0) + (c.y - (d.y || 0)) * s * alpha;
        });
      })
      .alpha(0.5).alphaMin(0.01).alphaDecay(0.03).velocityDecay(0.4)
      .on("tick", () => {
        link.attr("x1", (d) => (d.source as GraphNode).x!).attr("y1", (d) => (d.source as GraphNode).y!)
          .attr("x2", (d) => (d.target as GraphNode).x!).attr("y2", (d) => (d.target as GraphNode).y!);
        linkLabel.attr("x", (d) => ((d.source as GraphNode).x! + (d.target as GraphNode).x!) / 2)
          .attr("y", (d) => ((d.source as GraphNode).y! + (d.target as GraphNode).y!) / 2);
        node.attr("cx", (d) => d.x!).attr("cy", (d) => d.y!);
        label.attr("x", (d) => d.x!).attr("y", (d) => d.y!);
      });

    simulationRef.current = simulation;

    const observer = new ResizeObserver(([entry]) => {
      const { width: w, height: h } = entry.contentRect;
      svg.attr("width", w).attr("height", h);
      simulation.force("center", d3.forceCenter(w / 2, h / 2));
      simulation.alpha(0.1).restart();
    });
    observer.observe(container);

    return () => { simulation.stop(); observer.disconnect(); };
  }, [data, getFilteredData, onNodeClick]);

  // ========== SEPARATE EFFECT: Apply highlights without re-creating graph ==========
  useEffect(() => {
    const state = d3StateRef.current;
    if (!state) return;

    const { node, link, label, linkLabel, connectedMap, nodes } = state;
    const highlighted = new Set<string>(highlightNodeIds);
    if (highlightNodeId) highlighted.add(highlightNodeId);

    if (highlighted.size === 0) {
      // Reset to default
      node.attr("opacity", 1)
        .attr("stroke", "#ffffff30")
        .attr("stroke-width", 1);
      link.attr("stroke", "#333").attr("stroke-opacity", 0.2).attr("stroke-width", 0.7);
      label.attr("opacity", 0.7);
      linkLabel.attr("visibility", "hidden");
      return;
    }

    // Collect all neighbors of highlighted nodes
    const allNeighbors = new Set<string>();
    highlighted.forEach((id) => {
      const neighbors = connectedMap.get(id);
      if (neighbors) neighbors.forEach((n) => allNeighbors.add(n));
    });

    const isRelevant = (id: string) => highlighted.has(id) || allNeighbors.has(id);
    const isLinkRelevant = (l: GraphLink) => {
      const src = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const tgt = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      return highlighted.has(src) || highlighted.has(tgt);
    };

    // Nodes: highlighted=gold ring, neighbors=visible, rest=faded
    node.attr("opacity", (d) => isRelevant(d.id) ? 1 : 0.08)
      .attr("stroke", (d) => {
        if (highlighted.has(d.id)) return "#FFD700";
        if (allNeighbors.has(d.id)) return "#ffffff80";
        return "#ffffff10";
      })
      .attr("stroke-width", (d) => highlighted.has(d.id) ? 4 : allNeighbors.has(d.id) ? 2 : 0.5);

    // Links: connected=colored+thick, rest=nearly invisible
    link.attr("stroke", (l) => isLinkRelevant(l) ? (EDGE_COLORS[l.type] || "#888") : "#222")
      .attr("stroke-opacity", (l) => isLinkRelevant(l) ? 0.9 : 0.03)
      .attr("stroke-width", (l) => isLinkRelevant(l) ? 2.5 : 0.5);

    // Labels: only show for highlighted + neighbors
    label.attr("opacity", (d) => isRelevant(d.id) ? 1 : 0.04);

    // Edge labels: show for connected edges
    linkLabel.attr("visibility", (l) => isLinkRelevant(l) ? "visible" : "hidden")
      .attr("fill", (l) => EDGE_COLORS[l.type] || "#aaa");

    // Auto-zoom to highlighted nodes
    if (svgRef.current && zoomRef.current) {
      const svg = d3.select(svgRef.current);
      const zoom = zoomRef.current;
      const container = svg.node()!.parentElement!;
      const width = container.clientWidth;
      const height = container.clientHeight;

      const hn = nodes.filter((n) => highlighted.has(n.id));
      if (hn.length === 1 && hn[0].x != null) {
        const n = hn[0];
        svg.transition().duration(750).call(zoom.transform,
          d3.zoomIdentity.translate(width / 2, height / 2).scale(1.5).translate(-(n.x ?? 0), -(n.y ?? 0)));
      } else if (hn.length > 1) {
        const positioned = hn.filter((n) => n.x != null);
        if (positioned.length > 0) {
          const [x0, x1] = d3.extent(positioned, (n) => n.x) as [number, number];
          const [y0, y1] = d3.extent(positioned, (n) => n.y) as [number, number];
          const s = Math.min(0.8 * width / Math.max(x1 - x0 + 100, 1), 0.8 * height / Math.max(y1 - y0 + 100, 1), 2);
          svg.transition().duration(750).call(zoom.transform,
            d3.zoomIdentity.translate(width / 2, height / 2).scale(s).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
        }
      }
    }
  }, [highlightNodeId, highlightNodeIds]);

  return (
    <div style={{ width: "100%", height: "100%", background: "#0f0f1a", position: "relative" }}>
      <svg ref={svgRef} style={{ width: "100%", height: "100%" }} />
      <div ref={tooltipRef} style={{
        position: "fixed", background: "rgba(20,20,30,0.95)", border: "1px solid #444",
        borderRadius: 6, padding: "8px 12px", color: "#eee", fontSize: 12,
        pointerEvents: "none", opacity: 0, zIndex: 1000, transition: "opacity 0.1s",
      }} />
    </div>
  );
});

export default GraphCanvas;
