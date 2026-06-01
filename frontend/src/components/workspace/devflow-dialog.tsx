"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";

interface DevFlowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (name: string, description: string) => void;
}

export function DevFlowDialog({ open, onOpenChange, onSubmit }: DevFlowDialogProps) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleSubmit = () => {
    if (!name.trim()) return;
    onSubmit(name.trim(), description.trim());
    setName("");
    setDescription("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>启动代码全流程开发</DialogTitle>
          <DialogDescription>
            创建一个新的代码开发项目，系统将自动完成从需求分析到部署的完整流程。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <label htmlFor="name" className="text-sm font-medium">
              项目名称
            </label>
            <Input
              id="name"
              placeholder="输入项目名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <label htmlFor="description" className="text-sm font-medium">
              项目描述
            </label>
            <Textarea
              id="description"
              placeholder="描述项目需求和目标"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
            />
          </div>

          <div className="rounded-lg border bg-muted/50 p-4">
            <h4 className="mb-2 text-sm font-medium">开发流程</h4>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>📋 需求分析</span>
              <span>→</span>
              <span>🏗️ 架构设计</span>
              <span>→</span>
              <span>💻 代码开发</span>
              <span>→</span>
              <span>🧪 测试</span>
              <span>→</span>
              <span>🚀 部署</span>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={!name.trim()}>
            启动开发流程
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
