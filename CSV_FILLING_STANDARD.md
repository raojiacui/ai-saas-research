# CSV 填写标准

这份规范用于维护本仓库的 `products.csv`、`demands.csv`、`backlinks.csv`、`revenue-products.csv` 等 CSV 文件，目标是让 GitHub 和常见表格工具都能稳定渲染成表格

## 核心原则

- 每个 CSV 文件第一行必须是表头
- 每一条数据必须占一个物理行，不要在单元格里直接换行
- 每一行的列数必须和表头一致
- 使用英文逗号 `,` 作为列分隔符
- 字段内容里如果包含英文逗号 `,`、英文双引号 `"` 或换行，必须按标准 CSV 规则转义
- 不要使用未转义的英文双引号，这是最容易导致表格渲染失败的问题

## 字段转义规则

普通字段可以直接写：

```csv
Viggle AI,https://www.viggle.ai/,meme创作者
```

字段里包含英文逗号时，整个字段必须用英文双引号包起来：

```csv
"销售赋能,员工培训,教程视频制作"
```

字段里包含英文双引号时，整个字段必须用英文双引号包起来，并把内部每个 `"` 写成两个 `""`：

```csv
"明确的""Clone Video Ads""能力"
```

不要写成下面这样：

```csv
明确的"Clone Video Ads"能力
```

字段里原本有多行内容时，改成单行表达，推荐用 ` / `、`;`、`；` 分隔：

```csv
"Free：$0 / Pro：$14.9/月 / Ultra：$59.9/月"
```

## 分隔行和备注行

如果需要区分人工整理和自动化补充，可以像 `demands.csv` 一样保留标记行，但必须补齐列数：

```csv
,,,,,
以下是Agent自动化找的,,,,,
```

更推荐的做法是不要在 CSV 中插入分隔行，而是在新增一列中标注来源，例如：

```csv
产品名,网址,来源
Domo AI,https://www.domoai.app/,Agent自动化
```

## 编辑建议

- 优先用表格软件、脚本或 CSV 导出工具编辑，不要手工拼复杂字段
- 如果手工编辑，看到英文逗号或英文双引号时，立刻检查是否需要加引号和转义
- 中文逗号 `，`、顿号 `、`、中文分号 `；` 不会切分列，可以正常使用
- 英文逗号 `,` 会切分列，除非字段整体已经用英文双引号包起来
- 不要混用奇怪的智能引号，例如 `“`、`”` 来代替 CSV 的英文双引号

## 提交前检查

在 PowerShell 中运行下面的检查。以 `products.csv` 为例：

```powershell
$path = 'products.csv'
$rows = Import-Csv -LiteralPath $path
$headers = $rows[0].PSObject.Properties.Name
"rows=$($rows.Count) columns=$($headers.Count)"
```

如果要检查每个物理行是否列数一致，可以运行：

```powershell
$path = 'products.csv'
$expected = (Get-Content -LiteralPath $path -TotalCount 1).Split(',').Count
$lines = [System.IO.File]::ReadAllLines((Resolve-Path $path))
$bad = @()
foreach ($lineNo in 1..$lines.Count) {
  $line = $lines[$lineNo - 1]
  $inQuotes = $false
  $cols = 1
  for ($i = 0; $i -lt $line.Length; $i++) {
    $c = $line[$i]
    if ($c -eq '"') {
      if ($inQuotes -and $i + 1 -lt $line.Length -and $line[$i + 1] -eq '"') { $i++ }
      else { $inQuotes = -not $inQuotes }
    } elseif ($c -eq ',' -and -not $inQuotes) {
      $cols++
    }
  }
  if ($inQuotes -or $cols -ne $expected) {
    $bad += [pscustomobject]@{ Line = $lineNo; Columns = $cols; OpenQuote = $inQuotes }
  }
}
if ($bad.Count) { $bad | Format-Table -AutoSize } else { 'CSV line check OK' }
```

同时建议运行：

```powershell
git diff --check
```

## 常见错误

- 字段里写了英文双引号但没有转义，例如 `"Clone Video Ads"`
- 字段里有英文逗号但没有把整个字段包进英文双引号
- 从网页复制内容时带入了换行，导致一条记录拆成多行
- 空行或备注行没有补齐逗号，导致列数不一致
- 文件不是 `.csv` 扩展名，或者文件名大小写和引用位置不一致
