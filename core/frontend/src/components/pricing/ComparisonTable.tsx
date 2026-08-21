import { Check, X } from 'lucide-react'

type CellValue = string | boolean

interface Row {
  feature: string
  free: CellValue
  plus: CellValue
  pro: CellValue
}

const ROWS: Row[] = [
  { feature: 'Image generations', free: '5 / week', plus: '50 / week', pro: '500 / week' },
  { feature: 'Voice rooms', free: false, plus: '5 / week', pro: '30 / week' },
  { feature: 'Code sessions', free: false, plus: '20 / week', pro: '200 / week' },
  { feature: 'Knowledge base storage', free: '50 MB', plus: '1 GB', pro: '10 GB' },
  { feature: 'Knowledge base docs', free: 'Limited', plus: '100 docs', pro: 'Unlimited' },
  { feature: 'BYOK support', free: true, plus: true, pro: true },
  { feature: 'Support level', free: false, plus: 'Email', pro: 'Priority' },
]

function Cell({ value }: { value: CellValue }) {
  if (typeof value === 'boolean') {
    return value ? (
      <Check className="h-4 w-4 text-brand-500 mx-auto" />
    ) : (
      <X className="h-4 w-4 text-muted-foreground mx-auto" />
    )
  }
  return <span className="text-sm">{value}</span>
}

export function ComparisonTable() {
  return (
    <div className="hidden md:block overflow-x-auto">
      <table className="w-full max-w-4xl mx-auto text-sm border-collapse">
        <thead>
          <tr className="border-b-2 border-foreground/40">
            <th className="text-left py-3 pr-6 font-medium text-muted-foreground w-1/3">Feature</th>
            <th className="text-center py-3 px-4 font-semibold">Free</th>
            <th className="text-center py-3 px-4 font-semibold text-primary">Plus</th>
            <th className="text-center py-3 px-4 font-semibold">Pro</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row, i) => (
            <tr
              key={row.feature}
              className={`border-b border-border/50 ${i % 2 === 0 ? 'bg-muted/20' : ''}`}
            >
              <td className="py-3 pr-6 text-muted-foreground">{row.feature}</td>
              <td className="py-3 px-4 text-center">
                <Cell value={row.free} />
              </td>
              <td className="py-3 px-4 text-center">
                <Cell value={row.plus} />
              </td>
              <td className="py-3 px-4 text-center">
                <Cell value={row.pro} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
