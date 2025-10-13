FROM golang:1.23-alpine AS builder

# Install git and build dependencies
RUN apk add --no-cache git

# Clone vprox repository
RUN git clone https://github.com/modal-labs/vprox.git /src

WORKDIR /src

# Build vprox binary from root (main.go)
RUN go build -o vprox .

FROM alpine:latest

# Install WireGuard tools
RUN apk add --no-cache wireguard-tools iptables

# Copy vprox binary
COPY --from=builder /src/vprox /usr/local/bin/vprox

# Run connect command by default (will need server IP as argument)
ENTRYPOINT ["vprox", "connect"]
