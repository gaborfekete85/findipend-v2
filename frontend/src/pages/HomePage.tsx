import { useAuth } from "@clerk/react";
import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import SummaryWidgets, { PositionsTable, type Position, type Summary } from "../components/SummaryWidgets";

export default function HomePage() {
  const { getToken } = useAuth();
  const [overview, setOverview] = useState<(Summary & { assets: Position[] }) | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Summary & { assets: Position[] }>("/api/v1/summary", getToken).then(setOverview, (e: unknown) =>
      setError(e instanceof Error ? e.message : "Request failed"),
    );
  }, [getToken]);

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8">
      <h1 className="text-3xl font-bold">Findipend</h1>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {overview && (
        <>
          <SummaryWidgets summary={overview} />
          <PositionsTable name="Assets" positions={overview.assets} />
        </>
      )}
    </main>
  );
}
