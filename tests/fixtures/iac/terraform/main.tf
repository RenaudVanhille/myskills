provider "aws" {
  region = "eu-west-3"
}

resource "aws_vpc" "prod" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.prod.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
}

resource "aws_subnet" "app" {
  vpc_id     = aws_vpc.prod.id
  cidr_block = "10.0.2.0/24"
}

resource "aws_subnet" "data" {
  vpc_id     = aws_vpc.prod.id
  cidr_block = "10.0.3.0/24"
}

resource "aws_lb" "web" {
  name    = "web"
  subnets = [aws_subnet.public.id]
  # { accolade dans un commentaire
}

resource "aws_ecs_service" "api" {
  name          = "api-commandes"
  desired_count = 3
  network_configuration {
    subnets = [aws_subnet.app.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
  }
  depends_on = [aws_db_instance.orders, aws_sqs_queue.orders]
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.web.arn
  port              = 443
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_target_group" "api" {
  vpc_id = aws_vpc.prod.id
}

resource "aws_db_instance" "orders" {
  identifier           = "commandes"
  db_subnet_group_name = aws_db_subnet_group.data.name
}

resource "aws_db_subnet_group" "data" {
  subnet_ids = [aws_subnet.data.id]
}

resource "aws_sqs_queue" "orders" {
  name = "commandes"
}

resource "aws_lambda_function" "billing" {
  function_name = "facturation"
  role          = aws_iam_role.billing.arn
  environment {
    variables = {
      BUCKET = aws_s3_bucket.invoices.bucket
      NOTE   = "texte avec } accolade"
    }
  }
}

resource "aws_lambda_event_source_mapping" "orders" {
  event_source_arn = aws_sqs_queue.orders.arn
  function_name    = aws_lambda_function.billing.arn
}

resource "aws_s3_bucket" "invoices" {
  bucket = "factures"
}

resource "aws_iam_role" "billing" {
  name = "billing"
}
