set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Machine JDK for the tv recipe; a real JAVA_HOME always wins.
export JAVA_HOME := env_var_or_default("JAVA_HOME", "C:/Users/Dell/AppData/Local/Programs/Microsoft/jdk-17.0.10.7-hotspot")

# Stack region for the deploy recipes; must match samconfig.toml.
export AWS_DEFAULT_REGION := env_var_or_default("PORCH_REGION", "ap-southeast-2")

check-prose:
    uv run scripts/check_prose.py

[working-directory: 'backend']
backend:
    uv run ruff check
    uv run ruff format --check
    uv run mypy
    uv run pytest --cov=porch.domain --cov=porch.adapters --cov=porch.api --cov-report=term-missing --cov-fail-under=90

[working-directory: 'tv']
tv:
    ./gradlew.bat spotlessCheck detekt lint testDebugUnitTest verifyRoborazziDebug assembleRelease

[working-directory: 'echo']
echo:
    # .cmd so the Windows PowerShell execution policy does not block pnpm.ps1.
    pnpm.cmd install --frozen-lockfile
    pnpm.cmd exec biome ci
    pnpm.cmd exec tsc --noEmit
    pnpm.cmd exec vitest run
    pnpm.cmd build

[working-directory: 'backend']
echo-fixtures:
    uv run python -m porch echo-fixtures

check: check-prose backend tv echo

[working-directory: 'backend']
contracts:
    uv run python -m porch export-contracts --out ../contracts
    git -C .. diff --exit-code contracts

[working-directory: 'backend']
demo:
    uv run python -m porch demo --serve

# Lambda packaging and deploy (needs AWS creds; secrets stay in SSM).
build-lambda:
    uv run scripts/build_lambda.py

deploy: build-lambda
    sam deploy --config-file infra/samconfig.toml

ring-token:
    $s = Read-Host -AsSecureString "Ring access token"; $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); aws ssm put-parameter --name /porch/ring/access_token --type SecureString --value $plain --overwrite | Out-Null; $plain = $null; Write-Output "stored /porch/ring/access_token"

house-key house="demo":
    $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes); $key = [Convert]::ToHexString($bytes).ToLower(); $sha = [BitConverter]::ToString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($key))).Replace("-","").ToLower(); aws ssm put-parameter --name "/porch/house/{{house}}/key_sha256" --type String --value $sha --overwrite | Out-Null; Write-Output "house key (show once, not stored): $key"

echo-deploy:
    $url = aws cloudformation describe-stacks --stack-name porch-ledger --query "Stacks[0].Outputs[?OutputKey=='McpUrl'].OutputValue" --output text; $bucket = aws cloudformation describe-stacks --stack-name porch-ledger --query "Stacks[0].Outputs[?OutputKey=='WebBucket'].OutputValue" --output text; $dist = aws cloudformation describe-stacks --stack-name porch-ledger --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text; $env:VITE_MCP_URL = $url; pnpm.cmd --dir echo build; aws s3 sync echo/dist "s3://$bucket" --delete; aws cloudfront create-invalidation --distribution-id $dist --paths "/*" | Out-Null; Write-Output "echo deployed, MCP at $url"
