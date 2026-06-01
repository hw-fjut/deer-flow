"use client";

import {
  ChevronRightIcon,
  ChevronDownIcon,
  FileIcon,
  FolderIcon,
  FolderOpenIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

import type { FileTreeNode as FileTreeNodeType } from "@/core/devflow/api";
import { getFileTree, readFile } from "@/core/devflow/api";

interface TreeNodeProps {
  node: FileTreeNodeType;
  depth?: number;
  onFileClick?: (node: FileTreeNodeType) => void;
  workspaceId: string;
}

function TreeNode({ node, depth = 0, onFileClick, workspaceId }: TreeNodeProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const isFolder = node.type === "folder";

  const handleClick = useCallback(async () => {
    if (isFolder) {
      // 如果是第一次点击文件夹，按需加载子节点
      if (!node.children && !isExpanded) {
        setIsLoading(true);
        try {
          const treeData = await getFileTree(workspaceId, 1);
          // 这里简化处理，实际应该只加载当前目录的子项
          // 由于后端已经返回了完整树，这里直接展开
        } catch {
          toast.error("加载文件夹失败");
        } finally {
          setIsLoading(false);
        }
      }
      setIsExpanded(!isExpanded);
    } else {
      onFileClick?.(node);
    }
  }, [isFolder, node.children, isExpanded, node, onFileClick, workspaceId]);

  return (
    <div>
      <div
        className={cn(
          "flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-sm transition-colors hover:bg-accent",
          depth > 0 && "ml-2",
          isLoading && "opacity-50",
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={handleClick}
      >
        {isFolder ? (
          <>
            {isExpanded ? (
              <ChevronDownIcon className="h-3 w-3 shrink-0" />
            ) : (
              <ChevronRightIcon className="h-3 w-3 shrink-0" />
            )}
            {isExpanded ? (
              <FolderOpenIcon className="h-3 w-3 shrink-0 text-yellow-500" />
            ) : (
              <FolderIcon className="h-3 w-3 shrink-0 text-yellow-500" />
            )}
          </>
        ) : (
          <>
            <span className="w-3" />
            <FileIcon className="h-3 w-3 shrink-0 text-muted-foreground" />
          </>
        )}
        <span className="truncate">{node.name}</span>
        {isLoading && (
          <span className="ml-auto text-xs text-muted-foreground">加载中...</span>
        )}
      </div>
      {isFolder && isExpanded && node.children && node.children.length > 0 && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              onFileClick={onFileClick}
              workspaceId={workspaceId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface FileTreeProps {
  workspaceName: string;
  workspacePath: string;
  workspaceId: string;
  onFileClick?: (node: FileTreeNodeType) => void;
}

export function FileTree({ workspaceName, workspacePath, workspaceId, onFileClick }: FileTreeProps) {
  const [treeData, setTreeData] = useState<FileTreeNodeType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadFileTree() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getFileTree(workspaceId, 3); // 加载3层深度
        setTreeData(data.nodes);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load file tree";
        setError(message);
        toast.error(message);
      } finally {
        setIsLoading(false);
      }
    }

    if (workspaceId) {
      loadFileTree();
    }
  }, [workspaceId]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <FolderOpenIcon className="h-4 w-4" />
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-medium">{workspaceName}</p>
            <p className="truncate text-xs text-muted-foreground">
              {workspacePath}
            </p>
          </div>
        </div>
      </div>

      {/* File Tree */}
      <div className="flex-1 overflow-y-auto py-2">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            加载中...
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center text-sm text-destructive">
            {error}
          </div>
        ) : treeData.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <FolderIcon className="h-8 w-8 opacity-50" />
            <p>空目录</p>
          </div>
        ) : (
          treeData.map((node) => (
            <TreeNode
              key={node.path}
              node={node}
              onFileClick={onFileClick}
              workspaceId={workspaceId}
            />
          ))
        )}
      </div>
    </div>
  );
}
