import { useEffect, useRef } from 'react';

export type ActiveTool =
  | 'DikkatUyarisi'
  | 'MolaOnerisi'
  | 'OgrenmePeriyoduOnerisi'
  | 'ZihinYorgunluguTahmini'
  | 'OgrenmeTarziTahmini'
  | 'OturumOzeti'
  | 'SoruyaGoreAnalizYap'
  | 'SesOzetPDF';

export interface ActiveToolsResponse {
  active_tools: ActiveTool[];
}

export interface ActiveToolResult {
  tool: ActiveTool;
  priority: number;
}

const TOOL_PRIORITIES: Record<ActiveTool, number> = {
  SoruyaGoreAnalizYap: 1,
  ZihinYorgunluguTahmini: 2,
  MolaOnerisi: 3,
  DikkatUyarisi: 4,
  OgrenmePeriyoduOnerisi: 5,
  OgrenmeTarziTahmini: 6,
  OturumOzeti: 7,
  SesOzetPDF: 8,
};

export function getHighestPriorityTool(tools: ActiveTool[]): ActiveToolResult | null {
  if (!tools || tools.length === 0) return null;
  let sorted = tools
    .map(tool => ({ tool, priority: TOOL_PRIORITIES[tool] ?? 99 }))
    .sort((a, b) => a.priority - b.priority);
  return sorted[0] || null;
}

export function useActiveTools(onToolChange: (tool: ActiveToolResult | null) => void, pollInterval = 1000) {
  const lastToolRef = useRef<ActiveTool | null>(null);

  useEffect(() => {
    let isMounted = true;
    const poll = async () => {
      try {
        const res = await fetch('http://localhost:8005/active_tools');
        if (!res.ok) return;
        const data: ActiveToolsResponse = await res.json();
        const result = getHighestPriorityTool(data.active_tools);
        if (isMounted && result?.tool !== lastToolRef.current) {
          lastToolRef.current = result?.tool || null;
          onToolChange(result);
        }
      } catch {}
    };
    const interval = setInterval(poll, pollInterval);
    poll();
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [onToolChange, pollInterval]);
}
