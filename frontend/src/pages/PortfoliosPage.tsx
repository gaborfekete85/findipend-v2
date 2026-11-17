import { useAuth } from "@clerk/react";
import { type FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api/client";

type Portfolio = { id: number; name: string; created_at: string; updated_at: string };

const PATH = "/api/v1/portfolios";

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

function message(error: unknown) {
  return error instanceof Error ? error.message : "Request failed";
}

export default function PortfoliosPage() {
  const { getToken } = useAuth();
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  const [loadError, setLoadError] = useState("");

  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState("");

  const [renaming, setRenaming] = useState<Portfolio | null>(null);
  const [renameTo, setRenameTo] = useState("");
  const [renameError, setRenameError] = useState("");

  const [deleting, setDeleting] = useState<Portfolio | null>(null);
  const [confirmName, setConfirmName] = useState("");
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    apiFetch<Portfolio[]>(PATH, getToken)
      .then(setPortfolios)
      .catch((error: unknown) => setLoadError(message(error)));
  }, [getToken]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setCreateError("");
    try {
      const created = await apiFetch<Portfolio>(PATH, getToken, jsonInit("POST", { name: newName }));
      setPortfolios((list) => [...(list ?? []), created]);
      setNewName("");
    } catch (error) {
      setCreateError(message(error));
    }
  }

  async function rename(event: FormEvent) {
    event.preventDefault();
    if (!renaming) return;
    setRenameError("");
    try {
      const renamed = await apiFetch<Portfolio>(
        `${PATH}/${renaming.id}`,
        getToken,
        jsonInit("PATCH", { name: renameTo }),
      );
      setPortfolios((list) => (list ?? []).map((p) => (p.id === renamed.id ? renamed : p)));
      setDeleting((open) => (open?.id === renamed.id ? renamed : open));
      setRenaming(null);
    } catch (error) {
      setRenameError(message(error));
    }
  }

  async function remove() {
    if (!deleting || confirmName !== deleting.name) return;
    setDeleteError("");
    try {
      await apiFetch<void>(
        `${PATH}/${deleting.id}`,
        getToken,
        jsonInit("DELETE", { confirm_name: confirmName }),
      );
      setPortfolios((list) => (list ?? []).filter((p) => p.id !== deleting.id));
      setDeleting(null);
    } catch (error) {
      setDeleteError(message(error));
    }
  }

  function startRename(portfolio: Portfolio) {
    setRenaming(portfolio);
    setRenameTo(portfolio.name);
    setRenameError("");
  }

  function startDelete(portfolio: Portfolio) {
    setDeleting(portfolio);
    setConfirmName("");
    setDeleteError("");
  }

  return (
    <main className="mx-auto max-w-xl space-y-6 p-8">
      <h1 className="text-3xl font-bold">Portfolios</h1>

      <form aria-label="Create portfolio" onSubmit={create} className="space-y-1">
        <div className="flex gap-2">
          <input
            aria-label="New portfolio name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="flex-1 rounded border px-2 py-1"
          />
          <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-white">
            Create
          </button>
        </div>
        {createError && (
          <p role="alert" className="text-sm text-red-600">
            {createError}
          </p>
        )}
      </form>

      {loadError && (
        <p role="alert" className="text-red-600">
          {loadError}
        </p>
      )}

      {portfolios && (
        <ul aria-label="Portfolios" className="divide-y rounded border">
          {portfolios.map((portfolio) => (
            <li key={portfolio.id} className="flex items-center gap-2 p-2">
              {renaming?.id === portfolio.id ? (
                <form onSubmit={rename} className="flex flex-1 flex-wrap gap-2">
                  <input
                    aria-label={`New name for ${portfolio.name}`}
                    value={renameTo}
                    onChange={(e) => setRenameTo(e.target.value)}
                    className="flex-1 rounded border px-2 py-1"
                  />
                  <button type="submit" className="rounded border px-2 py-1">
                    Save
                  </button>
                  <button type="button" onClick={() => setRenaming(null)} className="rounded border px-2 py-1">
                    Cancel
                  </button>
                  {renameError && (
                    <p role="alert" className="w-full text-sm text-red-600">
                      {renameError}
                    </p>
                  )}
                </form>
              ) : (
                <>
                  <span data-portfolio-name className="flex-1">
                    <a href={`/portfolios/${portfolio.id}`}>{portfolio.name}</a>
                  </span>
                  <button
                    type="button"
                    aria-label={`Rename ${portfolio.name}`}
                    onClick={() => startRename(portfolio)}
                    className="rounded border px-2 py-1"
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${portfolio.name}`}
                    onClick={() => startDelete(portfolio)}
                    className="rounded border px-2 py-1 text-red-600"
                  >
                    Delete
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {deleting && (
        <div
          role="dialog"
          aria-label={`Delete ${deleting.name}`}
          className="space-y-2 rounded border border-red-300 p-4"
        >
          <p>This deletes {deleting.name} with all its buys, sells and allocations.</p>
          <label className="block">
            Type {deleting.name} to confirm
            <input
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              className="mt-1 block w-full rounded border px-2 py-1"
            />
          </label>
          {deleteError && (
            <p role="alert" className="text-sm text-red-600">
              {deleteError}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              disabled={confirmName !== deleting.name}
              onClick={remove}
              className="rounded bg-red-600 px-3 py-1 text-white disabled:opacity-50"
            >
              Delete
            </button>
            <button type="button" onClick={() => setDeleting(null)} className="rounded border px-3 py-1">
              Cancel
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
