import { type Key, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  width?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => Key;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-ink-700/60 text-xs uppercase tracking-wider text-muted">
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={`px-3 py-2 font-medium ${
                  c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : ""
                }`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-ink-800/40 hover:bg-ink-800/30">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`px-3 py-2 text-slate-200 ${
                    c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : ""
                  }`}
                >
                  {c.render ? c.render(row) : ((row as Record<string, unknown>)[c.key] as ReactNode)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
