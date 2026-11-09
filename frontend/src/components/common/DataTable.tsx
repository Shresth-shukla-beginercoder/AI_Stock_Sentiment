import { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  emptyMessage?: string;
}

/**
 * Generic styled data table. Cells are rendered either from a column's `render`
 * or by reading `row[key]` as a string. No sorting logic baked in — that stays
 * at the page level when needed.
 */
export function DataTable<T>({ columns, rows, rowKey, emptyMessage = "No rows" }: DataTableProps<T>) {
  if (rows.length === 0) {
    return <p className="px-4 py-6 text-center text-sm text-muted">{emptyMessage}</p>;
  }

  const alignClass = (a?: "left" | "right" | "center") =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/5 text-xs uppercase tracking-wide text-muted">
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width }}
                className={`px-4 py-2.5 font-medium ${alignClass(col.align)}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className="border-b border-white/5 transition-colors last:border-0 hover:bg-bg-tertiary/40"
            >
              {columns.map((col) => (
                <td key={col.key} className={`px-4 py-2.5 text-text-primary ${alignClass(col.align)}`}>
                  {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
