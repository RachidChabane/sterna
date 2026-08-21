import {
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from '@/components/ui/dropdown-menu'
import { Copy, Download, FileText, Braces } from 'lucide-react'

interface ChatCopyExportItemsProps {
  onCopyResponses: () => void
  onCopyMetadata: () => void
  onExportResponses: () => void
  onExportMetadata: () => void
}

export function ChatCopyExportItems({
  onCopyResponses,
  onCopyMetadata,
  onExportResponses,
  onExportMetadata,
}: ChatCopyExportItemsProps) {
  return (
    <>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger>
          <FileText className="h-4 w-4 mr-2" /> Responses
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent>
          <DropdownMenuItem onClick={onCopyResponses}>
            <Copy className="h-4 w-4 mr-2" /> Copy
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onExportResponses}>
            <Download className="h-4 w-4 mr-2" /> Export (.txt)
          </DropdownMenuItem>
        </DropdownMenuSubContent>
      </DropdownMenuSub>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger>
          <Braces className="h-4 w-4 mr-2" /> Metadata
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent>
          <DropdownMenuItem onClick={onCopyMetadata}>
            <Copy className="h-4 w-4 mr-2" /> Copy (JSON)
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onExportMetadata}>
            <Download className="h-4 w-4 mr-2" /> Export (.json)
          </DropdownMenuItem>
        </DropdownMenuSubContent>
      </DropdownMenuSub>
    </>
  )
}
