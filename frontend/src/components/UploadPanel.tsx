import { useRef, useState } from "react";
import { uploadFile } from "../api/client";
import { useAuth } from "../api/AuthContext";

/**
 * Admin-gated file upload (FR1). Mirrors server-side RBAC: only the "admin"
 * role gets the button; the client-side check is cosmetic — the backend
 * enforces the same rule via require_admin (investigator -> 403).
 *
 * `onUploaded` fires after a SUCCESSFUL upload so the caller can refresh
 * analytics views (App bumps the InfluencerPanel refresh token).
 */
export function UploadPanel({ onUploaded }: { onUploaded?: () => void }) {
  const { role, token } = useAuth();
  const isAdmin = role === "admin";
  const fileRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<"/upload/cdr" | "/upload/fir">("/upload/cdr");
  const [message, setMessage] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setMessage(null);
    try {
      const res = (await uploadFile(kind, file)) as {
        records?: number;
        written?: boolean;
      };
      if (kind === "/upload/cdr") {
        setMessage(`CDR uploaded — ${res.records ?? 0} records ingested.`);
      } else {
        setMessage("FIR uploaded — entities extracted and written to the graph.");
      }
      onUploaded?.(); // new data landed -> analytics views should re-query
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 403) setMessage("Forbidden — this action requires the admin role.");
      else if (status === 422) setMessage("Rejected — invalid file format.");
      else setMessage("Upload failed — check the backend.");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (!token) return null; // only rendered behind the auth gate anyway

  return (
    <div className="border rounded p-4 bg-white">
      <h2 className="font-semibold mb-2">Upload Data</h2>
      {isAdmin ? (
        <div className="space-y-2">
          <select
            className="border rounded px-2 py-1 text-sm w-full"
            value={kind}
            onChange={(e) => setKind(e.target.value as "/upload/cdr" | "/upload/fir")}
          >
            <option value="/upload/cdr">CDR (CSV)</option>
            <option value="/upload/fir">FIR (TXT)</option>
          </select>
          <input
            ref={fileRef}
            type="file"
            accept={kind === "/upload/cdr" ? ".csv,text/csv" : ".txt,text/plain"}
            onChange={handleFile}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded file:border-0 file:bg-indigo-600 file:text-white file:px-3 file:py-1.5 file:text-sm file:hover:bg-indigo-700"
          />
          {message && <p className="text-sm text-slate-600">{message}</p>}
        </div>
      ) : (
        <p className="text-sm text-slate-500">
          Uploads require the <strong>admin</strong> role. You are logged in as an
          investigator.
        </p>
      )}
    </div>
  );
}
