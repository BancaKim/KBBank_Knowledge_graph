import { useState, useCallback, useRef } from "react";
import type { Product } from "../types/graph";
import { API_BASE } from "../config";

export function useSearch() {
  const [results, setResults] = useState<Product[]>([]);
  const [searching, setSearching] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const search = useCallback((query: string, category?: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);

    if (!query.trim()) {
      setResults([]);
      return;
    }

    timerRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const params = new URLSearchParams({ q: query });
        if (category) params.set("category", category);
        const res = await fetch(`${API_BASE}/search?${params}`);
        if (!res.ok) throw new Error("Search failed");
        const json = await res.json();
        setResults(json.products || json);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  }, []);

  const clear = useCallback(() => {
    setResults([]);
  }, []);

  return { results, searching, search, clear };
}
