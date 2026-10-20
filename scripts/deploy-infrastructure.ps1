param(
  [string]$StackName = "nexus-mind",
  [string]$Region = "ap-southeast-2",
  [string]$Profile = "nexus-mind",
  [Parameter(Mandatory = $true)][string]$SenderEmail,
  [Parameter(Mandatory = $true)][string]$SesIdentity,
  [string]$BedrockModelId = "global.amazon.nova-2-lite-v1:0"
)

$ErrorActionPreference = "Stop"
if ($SenderEmail -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') { throw "SenderEmail must be a valid address verified in SES." }
if ([string]::IsNullOrWhiteSpace($SesIdentity)) { throw "SesIdentity must match the verified SES email or domain." }

$workspace = Split-Path -Parent $PSScriptRoot
Push-Location $workspace
try {
  sam build --template-file infra/template.yaml
  if ($LASTEXITCODE -ne 0) { throw "SAM build failed; no AWS stack was deployed." }
  sam deploy --template-file .aws-sam/build/template.yaml --stack-name $StackName --region $Region --profile $Profile --capabilities CAPABILITY_NAMED_IAM --resolve-s3 --parameter-overrides "SenderEmail=$SenderEmail" "SesIdentity=$SesIdentity" "BedrockModelId=$BedrockModelId" --confirm-changeset --no-fail-on-empty-changeset
  if ($LASTEXITCODE -ne 0) { throw "SAM deployment failed. Review the CloudFormation stack events in the selected Region." }
  Write-Host "Infrastructure deployment completed in $Region. Upload the generated dataset and website with scripts/deploy-frontend.ps1."
}
finally {
  Pop-Location
}
