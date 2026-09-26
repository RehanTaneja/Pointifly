import { ResponsiveContainer, Sankey, Tooltip } from 'recharts'
import type { NodeProps } from 'recharts/types/chart/Sankey'
import { fmtPts, type OptimizeResponse } from '../api'

// Sink nodes (trips, Preserved) get their label on the left so it stays inside the chart.
// In recharts, targetLinks are a node's outgoing links, so sinks have none.
function FlowNode({ x, y, width, height, payload }: NodeProps) {
  const isSink = payload.targetLinks.length === 0
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill="var(--accent)" rx={2} />
      <text
        x={isSink ? x - 6 : x + width + 6}
        y={y + height / 2}
        textAnchor={isSink ? 'end' : 'start'}
        dominantBaseline="middle"
        className="sankey-label"
      >
        {payload.name} · {fmtPts(payload.value)}
      </text>
    </g>
  )
}

export function FlowSankey({ data }: { data: OptimizeResponse['sankey'] }) {
  return (
    <ResponsiveContainer width="100%" height={380}>
      <Sankey
        data={data}
        nodePadding={28}
        margin={{ top: 10, right: 10, bottom: 10, left: 10 }}
        node={(props: NodeProps) => <FlowNode {...props} />}
        link={{ stroke: 'var(--accent)', strokeOpacity: 0.25 }}
      >
        <Tooltip formatter={(v) => `${fmtPts(Number(v))} pts`} />
      </Sankey>
    </ResponsiveContainer>
  )
}
