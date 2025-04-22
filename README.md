# DeepSider API代理

这是一个将OpenAI API请求代理到DeepSider API的服务。

## 功能特点

- 支持OpenAI API的主要格式
- 直接使用DeepSider Token进行认证
- 自动映射模型名称
- 流式响应支持
- 多Token轮询支持
- 验证码显示功能
- 思维链(reasoning_content)支持

## 部署
### 使用 Docker 部署

#### 1. 安装 Docker（如果未安装）

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose -y
sudo systemctl enable --now docker

# CentOS
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install docker-ce docker-ce-cli containerd.io -y
sudo systemctl enable --now docker
```

#### 2. 克隆仓库并构建 Docker 镜像

```bash
# 克隆仓库
git clone https://github.com/yunqio/dsider.git
cd dsider

# 构建 Docker 镜像
sudo docker build -t dsider .
```

#### 3. 运行 Docker 容器

```bash
# 启动容器，映射端口 7860 到宿主机，并命名容器为dsider
sudo docker run -d -p 7860:7860 --name dsider dsider
```
### dockerhub部署

使用DockerHub上的预构建镜像可以更加方便地部署本服务，无需克隆代码和手动构建：

```bash
# 拉取DockerHub上的镜像
sudo docker pull 958527256docker/dsider:latest

# 运行容器，映射端口7860到宿主机，并命名容器为dsider
sudo docker run -d -p 7860:7860 --name dsider 958527256docker/dsider:latest



### 使用Docker Compose部署
sudo docker-compose up -d


```

### 直接部署

如果你想不使用 Docker 直接部署应用：

#### 1. 安装必要的系统依赖

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv git -y

# CentOS
sudo yum install python3 python3-pip git -y
```

#### 2. 克隆代码并设置环境

```bash
# 克隆仓库
git clone https://github.com/yunqio/dsider.git
cd dsider

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

#### 3. 配置环境变量（可选）

```bash
# 如果需要自定义端口
cp env .env
nano .env  # 编辑端口号等配置
```

#### 4. 启动应用

```bash
# 直接启动
python app.py

# 或使用 uvicorn 启动（需要先安装：pip install uvicorn）
uvicorn app:app --host 0.0.0.0 --port 7860
```
