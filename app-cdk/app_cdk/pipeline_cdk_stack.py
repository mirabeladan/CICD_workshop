import os
from constructs import Construct
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_codeconnections as codeconnections,
    aws_codepipeline as codepipeline,
    aws_codebuild as codebuild,
    aws_codepipeline_actions as codepipeline_actions,
    aws_iam as iam,
    aws_ssm as ssm,
)

class PipelineCdkStack(Stack):

    def __init__(self, scope: Construct, id: str, ecr_repository, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Creates a CodeConnections resource called 'CICD_Workshop_Connection'
        SourceConnection = codeconnections.CfnConnection(self, "CICD_Workshop",
                connection_name="CICD_Workshop_Connection",
                provider_type="GitHub",
        )

        pipeline = codepipeline.Pipeline(
            self, 'CICD_Pipeline',
            cross_account_keys = False,
            pipeline_type=codepipeline.PipelineType.V2,
            execution_mode=codepipeline.ExecutionMode.QUEUED
        )

        code_quality_build = codebuild.PipelineProject(
            self, 'Code Quality',
            build_spec = codebuild.BuildSpec.from_source_filename('./buildspec_test.yml'),
            environment = codebuild.BuildEnvironment(
                build_image = codebuild.LinuxBuildImage.STANDARD_5_0,
                privileged = True,
                compute_type = codebuild.ComputeType.LARGE,
            ),
        )

        docker_build_project = codebuild.PipelineProject(
            self, 'Docker Build',
            build_spec = codebuild.BuildSpec.from_source_filename('./buildspec_docker.yml'),
            environment = codebuild.BuildEnvironment(
                build_image = codebuild.LinuxBuildImage.STANDARD_5_0,
                privileged = True,
                compute_type = codebuild.ComputeType.LARGE,
                environment_variables = {
                    'IMAGE_TAG': codebuild.BuildEnvironmentVariable(
                        type = codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value = 'latest',
                    ),
                    'IMAGE_REPO_URI': codebuild.BuildEnvironmentVariable(
                        type = codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value = ecr_repository.repository_uri,
                    ),
                    'AWS_DEFAULT_REGION': codebuild.BuildEnvironmentVariable(
                        type = codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value = os.environ['CDK_DEFAULT_REGION'],
                    )
                }
            ),
        )
   
        docker_build_project.add_to_role_policy(iam.PolicyStatement(
            effect = iam.Effect.ALLOW,
            actions = [
                'ecr:GetAuthorizationToken',
                'ecr:BatchCheckLayerAvailability',
                'ecr:GetDownloadUrlForLayer',
                'ecr:GetRepositoryPolicy',
                'ecr:DescribeRepositories',
                'ecr:ListImages',
                'ecr:DescribeImages',
                'ecr:BatchGetImage',
                'ecr:InitiateLayerUpload',
                'ecr:UploadLayerPart',
                'ecr:CompleteLayerUpload',
                'ecr:PutImage',
            ],
            resources = ['*'],
        ))

        ssmParameter = ssm.StringParameter(
            self, 'SignerProfileARN',
            parameter_name='signer-profile-arn',
            string_value='arn:aws:signer:us-east-2:937871024262:/signing-profiles/ecr_signing_profile'
        )
   
        docker_build_project.add_to_role_policy(iam.PolicyStatement(
            effect = iam.Effect.ALLOW,
            actions = [
                'ssm:GetParametersByPath',
                'ssm:GetParameters',
            ],
            resources = ['*'],
        ))


        docker_build_project.add_to_role_policy(iam.PolicyStatement(
            effect = iam.Effect.ALLOW,
            actions = [
                'signer:PutSigningProfile',
                'signer:SignPayload',
                'signer:GetRevocationStatus'
            ],
            resources = ['*'],
        ))
   
        source_output = codepipeline.Artifact()
        unit_test_output = codepipeline.Artifact()
        docker_build_output = codepipeline.Artifact()

        source_action = codepipeline_actions.CodeStarConnectionsSourceAction(
          action_name = 'GitHub',
          owner = "mirabeladan",
          repo = "CICD_workshop",
          output = source_output,
          branch = "main",
          trigger_on_push = True,
          connection_arn = "arn:aws:codeconnections:us-east-2:937871024262:connection/034d83e4-67e1-448e-afae-a5f690d24139"
        )

        pipeline.add_stage(
          stage_name = 'Source',
          actions = [source_action]
        )

        build_action = codepipeline_actions.CodeBuildAction(
            action_name = 'Unit-Test',
            project = code_quality_build,
            input = source_output,  # The build action must use the CodeStarConnectionsSourceAction output as input.
            outputs = [unit_test_output],
        )

        pipeline.add_stage(
            stage_name = 'Code-Unit-Tests',
            actions = [build_action],
        )

        docker_build_action = codepipeline_actions.CodeBuildAction(
            action_name = 'Docker-Build',
            project = docker_build_project,
            input = source_output,
            outputs = [docker_build_output],
        )

        pipeline.add_stage(
            stage_name = 'Docker-Push-ECR',
            actions = [docker_build_action],
        )

        CfnOutput(
            self, 'SourceConnectionArn',
            value = SourceConnection.attr_connection_arn
        )

        CfnOutput(
            self, 'SourceConnectionStatus',
            value = SourceConnection.attr_connection_status
        )