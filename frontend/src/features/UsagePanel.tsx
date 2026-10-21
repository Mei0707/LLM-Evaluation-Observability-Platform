import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api, money, type UsageSummary } from "../api";
import { Badge, ErrorBox } from "../components/ui";
export function UsagePanel({ runId }: { runId: string }) {
  const data = useQuery({
    queryKey: ["usage", runId],
    queryFn: () =>
      api<{
        summary: UsageSummary;
        events: {
          id: string;
          scope: string;
          model: string;
          state: string;
          source: string;
          attempt_id: string;
          input_tokens: number | null;
          output_tokens: number | null;
          estimated_cost: number | null;
          input_rate: number | null;
          output_rate: number | null;
        }[];
      }>(`/runs/${runId}/usage`),
    refetchInterval: 2000,
  });
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h3>Usage ledger · every attempt</h3>
          <p>Generation, embeddings, judges, and application-reported usage</p>
        </div>
        <strong>
          {money(data.data?.summary.known_cost || 0)} known estimate
        </strong>
      </div>
      <ErrorBox error={data.error} />
      {data.data && !data.data.summary.complete && (
        <div className="info-box">
          Incomplete estimate: {data.data.summary.uncertain_calls} pending /
          uncertain calls, {data.data.summary.unpriced_calls} unpriced calls,{" "}
          {data.data.summary.legacy_results || 0} historical results without a
          ledger. Unknown usage is never represented as free.
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>STAGE / MODEL</th>
              <th>ATTEMPT</th>
              <th>STATE</th>
              <th>INPUT / OUTPUT TOKENS</th>
              <th>ESTIMATE</th>
              <th>SOURCE</th>
            </tr>
          </thead>
          <tbody>
            {data.data?.events.map((e) => (
              <tr key={e.id}>
                <td>
                  {e.scope}
                  <small className="trace-source">{e.model}</small>
                </td>
                <td className="mono">{e.attempt_id.slice(0, 8)}</td>
                <td>
                  <Badge status={e.state} />
                </td>
                <td>
                  {e.input_tokens ?? "unknown"} / {e.output_tokens ?? "unknown"}
                </td>
                <td>
                  {e.estimated_cost === null
                    ? "unknown / unpriced"
                    : money(e.estimated_cost)}
                </td>
                <td>{e.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel-bottom">
        {data.data?.summary.note ||
          "Durable request intents are written before inference is sent."}
      </div>
    </section>
  );
}
