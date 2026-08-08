$body = @{
    name = "Test Workflow"
    description = "A simple test workflow"
    definition = @{
        nodes = @(
            @{ id = "n1"; type = "input"; name = "Input"; config = @{ input_key = "topic"; default_value = "AI trends" } },
            @{ id = "n2"; type = "code"; name = "Process"; config = @{ code = 'output = {"greeting": "Hello " + str(inputs.get("topic", "world"))}' } },
            @{ id = "n3"; type = "output"; name = "Output"; config = @{} }
        )
        edges = @(
            @{ id = "e1"; source = "n1"; target = "n2" },
            @{ id = "e2"; source = "n2"; target = "n3" }
        )
    }
    input_schema = @{ type = "object" }
} | ConvertTo-Json -Depth 5

try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/workflows" -Method Post -Body $body -ContentType "application/json"
    $r | ConvertTo-Json -Depth 5
} catch {
    $_.Exception.Message
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $reader.ReadToEnd()
    }
}