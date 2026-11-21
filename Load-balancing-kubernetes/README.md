# Load Balancing Using Kubernetes Services

## 1. Project Overview

This experiment demonstrates load balancing in Kubernetes using a
Deployment and a NodePort Service. Multiple replicas of a web
application are deployed, and incoming HTTP requests are distributed
across the available Pods by the Kubernetes Service.

The experiment also demonstrates Kubernetes self-healing by deleting a
Pod and observing its automatic replacement, followed by scaling the
Deployment from three replicas to five replicas.

## 2. Objectives

1.   Deploy a containerized web application on Kubernetes.
2.   Create a Deployment with multiple replicas.
3.   Expose the application using a NodePort Service.
4.   Observe how a Kubernetes Service distributes requests across Pods.
5.   Demonstrate automatic Pod replacement using a Deployment.
6.   Scale the application from three replicas to five replicas.
7.   Compare request distribution before and after scaling.

## 3. Technologies Used

-   Kubernetes
-   Docker Desktop Kubernetes
-   kubectl
-   YAML
-   `traefik/whoami` container image
-   PowerShell

## 4. System Architecture

The following diagram shows the load-balancing setup used in this
experiment. The load-test client sends requests to the Kubernetes
Service, which forwards them to the available application Pods managed
by the Deployment.

![Kubernetes Load Balancing
Architecture](Kubernetes%20Load%20Balancing%20Architecture.png)

**Note:** The Service is configured as a NodePort Service on port
`30080`. The request-distribution tests were performed from a temporary
client Pod inside the cluster using the Service DNS name `lb-demo-svc`.

## 5. Project Structure

``` text
Load-balancing-kubernetes/
│
├── deployment.yaml
├── service.yaml
├── README.md
├── Kubernetes Load Balancing Architecture.png
│
└── screenshots/
    ├── 01_YAML_Configuration_and_Validation.png
    ├── 02_Deployment_Service_and_Three_Ready_Pods.png
    ├── 03_100_Requests_Load_Balancing_Results.png
    ├── 04_Pod_Deletion_and_Automatic_Replacement.png
    ├── 05_Scaling_From_Three_To_Five_Replicas.png
    └── 06_Load_Balancing_After_Scaling_To_Five_Pods.png
```

## 6. Implementation

### Step 1: Create a Kubernetes Namespace

A separate namespace was created to keep the experiment resources
isolated.

``` powershell
kubectl create namespace load-balancing
kubectl get namespaces
```

### Step 2: Create the Deployment

The Deployment uses the `traefik/whoami` image and initially creates
three replicas. Each Pod runs the application on port `80`.

Apply the Deployment:

``` powershell
kubectl apply -f deployment.yaml -n load-balancing
```

Verify the Deployment and Pods:

``` powershell
kubectl get deployments -n load-balancing
kubectl get pods -n load-balancing
```

### Step 3: Create the NodePort Service

The Service exposes the application on port `80` and is configured with
NodePort `30080`. It selects the Pods created by the Deployment.

Apply the Service:

``` powershell
kubectl apply -f service.yaml -n load-balancing
```

Verify the Service:

``` powershell
kubectl get services -n load-balancing
```

### Step 4: Verify the Initial Deployment

The application was initially deployed with three replicas. The
Deployment reported three available replicas, and all three Pods were in
the Running state.

``` powershell
kubectl get deployment,pods,svc -n load-balancing
```

### Step 5: Test Load Balancing with 100 Requests

A temporary client Pod using the `curlimages/curl` image was created
inside the cluster. It sent 100 HTTP requests to the Kubernetes Service
through its DNS name.

``` powershell
kubectl run lb-test --restart=Never --image=curlimages/curl -n load-balancing --command -- sh -c 'for i in $(seq 1 100); do curl -sS http://lb-demo-svc; done | grep "^Hostname:" | sort | uniq -c'
```

The hostname in each response identifies the Pod that handled that
request.

**Observed distribution across three Pods:**

  Pod           Requests handled
  ----------- ------------------
  Pod 1                       37
  Pod 2                       30
  Pod 3                       33
  **Total**              **100**

The requests were distributed across all three available Pods. The
distribution was not exactly equal because Kubernetes Service load
balancing does not guarantee strict round-robin distribution.

### Step 6: Demonstrate Self-Healing

One application Pod was deleted to demonstrate Kubernetes self-healing.

``` powershell
kubectl get pods -n load-balancing
kubectl delete pod <pod-name> -n load-balancing
kubectl get pods -n load-balancing -w
```

The Deployment's ReplicaSet detected that the number of available Pods
had fallen below the desired replica count and automatically created a
replacement Pod.

After the replacement became ready, the application again had three
running replicas.

### Step 7: Scale the Deployment to Five Replicas

The Deployment was scaled from three replicas to five replicas.

``` powershell
kubectl scale deployment lb-demo --replicas=5 -n load-balancing
kubectl get pods -n load-balancing
kubectl get deployment lb-demo -n load-balancing
```

Kubernetes created two additional Pods. The Deployment reached five
available replicas.

### Step 8: Test Load Balancing After Scaling

The client Pod sent another 100 HTTP requests to the same Kubernetes
Service.

``` powershell
kubectl run lb-test --restart=Never --image=curlimages/curl -n load-balancing --command -- sh -c 'for i in $(seq 1 100); do curl -sS http://lb-demo-svc; done | grep "^Hostname:" | sort | uniq -c'
```

**Observed distribution across five Pods:**

  Pod           Requests handled
  ----------- ------------------
  Pod 1                       23
  Pod 2                       30
  Pod 3                       15
  Pod 4                       20
  Pod 5                       12
  **Total**              **100**

After scaling, requests were distributed across all five Pods. The
counts were uneven, which is expected because Kubernetes Service routing
does not promise an exact equal or round-robin split.

## 7. Screenshots

### 7.1 YAML Configuration and Validation

![YAML Configuration and
Validation](screenshots/01_YAML_Configuration_and_Validation.png)

### 7.2 Deployment, Service, and Three Ready Pods

![Deployment, Service, and Three Ready
Pods](screenshots/02_Deployment_Service_and_Three_Ready_Pods.png)

### 7.3 Load Balancing Results for 100 Requests Across Three Pods

![100 Requests Load Balancing
Results](screenshots/03_100_Requests_Load_Balancing_Results.png)

### 7.4 Pod Deletion and Automatic Replacement

![Pod Deletion and Automatic
Replacement](screenshots/04_Pod_Deletion_and_Automatic_Replacement.png)

### 7.5 Scaling from Three to Five Replicas

![Scaling from Three to Five
Replicas](screenshots/05_Scaling_From_Three_To_Five_Replicas.png)

### 7.6 Load Balancing Results After Scaling to Five Pods

![Load Balancing After Scaling to Five
Pods](screenshots/06_Load_Balancing_After_Scaling_To_Five_Pods.png)

## 8. Final Verification

The final state of the experiment was verified using:

``` powershell
kubectl get deployment,pods,services -n load-balancing
```

The final Deployment had five available replicas, all five application
Pods were Running and Ready, and the NodePort Service was available.

## 9. Advantages of Kubernetes Load Balancing

-   **High availability:** Requests can be served by multiple
    application Pods.
-   **Scalability:** The number of replicas can be increased or
    decreased based on application requirements.
-   **Self-healing:** The Deployment automatically replaces failed or
    deleted Pods to maintain the desired replica count.
-   **Service discovery:** Pods can be accessed through a stable
    Kubernetes Service name.
-   **Better resource utilization:** Incoming requests can be handled by
    multiple application instances.

## 10. Conclusion

This experiment successfully demonstrated Kubernetes load balancing
using a NodePort Service and Deployment. Initially, the application was
deployed with three replicas, and 100 HTTP requests were distributed
across the three Pods. When one Pod was deleted, Kubernetes
automatically created a replacement, demonstrating self-healing.

The Deployment was then scaled from three replicas to five replicas. A
second set of 100 requests was distributed across the five Pods. The
experiment shows how Kubernetes Services provide a stable access point
for applications, while Deployments help maintain the desired number of
replicas and support scaling.

## 11. Author Details

-   **Name:** Shreenidhi Dharwad
-   **Department:** Computer Science and Engineering (AI)
-   **Semester:** 5th Semester
-   **Subject:** Cloud Computing
