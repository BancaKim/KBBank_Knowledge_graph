import { useState, useEffect, useCallback } from "react";
import type { GraphData } from "../types/graph";
import { API_BASE } from "../config";

export function useGraphData() {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async (filters?: { category?: string; node_type?: string }) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filters?.category) params.set("category", filters.category);
      if (filters?.node_type) params.set("node_type", filters.node_type);

      const url = `${API_BASE}/graph${params.toString() ? "?" + params.toString() : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch graph");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  return { data, loading, error, refetch: fetchGraph };
}
