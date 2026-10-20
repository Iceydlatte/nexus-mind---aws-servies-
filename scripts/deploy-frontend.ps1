param(
  [string]$StackName = "nexus-mind",
  [string]$Region = "ap-southeast-2",
  [string]$Profile = "nexus-mind"
)

$ErrorActionPreference = "Stop"
$awsCliDirectory = Join-Path $env:LOCALAPPDATA "Programs\Amazon\AWSCLIV2"
if (Test-Path (Join-Path $awsCliDirectory "aws.exe")) {
  $env:PATH = "$awsCliDirectory;$env:PATH"
}
$workspace = Split-Path -Parent $PSScriptRoot
Push-Location $workspace
try {
  python scripts/configure_aws_frontend.py --stack-name $StackName --region $Region --profile $Profile
  $outputs = aws cloudformation describe-stacks --stack-name $StackName --region $Region --profile $Profile --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0) { throw "Could not read CloudFormation outputs." }
  $values = @{}
  foreach ($output in $outputs) { $values[$output.OutputKey] = $output.OutputValue }
  if (-not $values.ContainsKey("WebsiteBucket") -or -not $values.ContainsKey("CloudFrontDistributionId") -or -not $values.ContainsKey("AppDataBucket")) {
    throw "The stack is missing a website, data bucket, or distribution output."
  }
  $dataset = "data/generated/activities.csv"
  if (-not (Test-Path $dataset)) {
    python scripts/generate_dataset.py
    if ($LASTEXITCODE -ne 0) { throw "Could not generate the synthetic training dataset. Install requirements.txt, then retry." }
  }
  aws s3 cp $dataset "s3://$($values['AppDataBucket'])/synthetic/activities.csv" --content-type "text/csv" --sse AES256 --region $Region --profile $Profile
  if ($LASTEXITCODE -ne 0) { throw "Synthetic dataset upload failed." }
  aws s3 sync frontend "s3://$($values['WebsiteBucket'])" --delete --region $Region --profile $Profile
  if ($LASTEXITCODE -ne 0) { throw "Website upload failed." }
  aws cloudfront create-invalidation --distribution-id $values["CloudFrontDistributionId"] --paths "/*" --profile $Profile
  if ($LASTEXITCODE -ne 0) { throw "CloudFront cache refresh failed." }
  Write-Host "Deployment submitted. Open $($values['WebsiteUrl']) after CloudFront finishes updating."
}
finally {
  Pop-Location
}
