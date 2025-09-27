"""
Async Docker Manager for non-blocking Docker operations.

This module provides an async wrapper around the Docker SDK to prevent
blocking the async event loop during container operations. It uses
asyncio.to_thread() to run blocking Docker operations in thread pools.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager
import docker
from docker.errors import DockerException, NotFound, APIError
import structlog

logger = structlog.get_logger(__name__)


class AsyncDockerManager:
    """
    Async wrapper around Docker SDK for non-blocking operations.

    Provides async versions of common Docker operations including:
    - Container creation, starting, stopping
    - Image building and management
    - Network operations
    - Volume management
    """

    def __init__(self, docker_client: docker.DockerClient, timeout_config):
        """
        Initialize async Docker manager.

        Args:
            docker_client: Existing Docker client instance
            timeout_config: Timeout configuration object
        """
        self.docker_client = docker_client
        self.timeout_config = timeout_config
        self._operation_semaphore = asyncio.Semaphore(10)  # Limit concurrent operations

    async def create_container(
        self,
        image: str,
        command: Optional[Union[str, List[str]]] = None,
        **kwargs
    ) -> Any:
        """
        Create a container asynchronously.

        Args:
            image: Docker image name
            command: Command to run in container
            **kwargs: Additional arguments for container creation

        Returns:
            Container object

        Raises:
            DockerException: If container creation fails
        """
        async with self._operation_semaphore:
            try:
                logger.debug("Creating container async",
                           image=image,
                           command=command)

                container = await asyncio.to_thread(
                    self.docker_client.containers.create,
                    image=image,
                    command=command,
                    **kwargs
                )

                logger.debug("Container created successfully",
                           container_id=container.id[:12])
                return container

            except Exception as e:
                logger.error("Failed to create container",
                           image=image,
                           error=str(e))
                raise

    async def start_container(self, container) -> None:
        """
        Start a container asynchronously.

        Args:
            container: Container object to start
        """
        async with self._operation_semaphore:
            try:
                logger.debug("Starting container async",
                           container_id=container.id[:12])

                await asyncio.to_thread(container.start)

                logger.debug("Container started successfully",
                           container_id=container.id[:12])

            except Exception as e:
                logger.error("Failed to start container",
                           container_id=container.id[:12],
                           error=str(e))
                raise

    async def stop_container(
        self,
        container,
        timeout: Optional[int] = None
    ) -> None:
        """
        Stop a container asynchronously.

        Args:
            container: Container object to stop
            timeout: Timeout for graceful shutdown
        """
        if timeout is None:
            timeout = self.timeout_config.container_stop_timeout

        async with self._operation_semaphore:
            try:
                logger.debug("Stopping container async",
                           container_id=container.id[:12],
                           timeout=timeout)

                await asyncio.to_thread(container.stop, timeout=timeout)

                logger.debug("Container stopped successfully",
                           container_id=container.id[:12])

            except Exception as e:
                logger.error("Failed to stop container",
                           container_id=container.id[:12],
                           error=str(e))
                raise

    async def remove_container(self, container, force: bool = False) -> None:
        """
        Remove a container asynchronously.

        Args:
            container: Container object to remove
            force: Force removal of running container
        """
        async with self._operation_semaphore:
            try:
                logger.debug("Removing container async",
                           container_id=container.id[:12],
                           force=force)

                await asyncio.to_thread(container.remove, force=force)

                logger.debug("Container removed successfully",
                           container_id=container.id[:12])

            except Exception as e:
                logger.error("Failed to remove container",
                           container_id=container.id[:12],
                           error=str(e))
                raise

    async def get_container(self, container_id: str):
        """
        Get container by ID asynchronously.

        Args:
            container_id: Container ID or name

        Returns:
            Container object
        """
        try:
            container = await asyncio.to_thread(
                self.docker_client.containers.get,
                container_id
            )
            return container
        except NotFound:
            logger.warning("Container not found",
                         container_id=container_id)
            raise
        except Exception as e:
            logger.error("Failed to get container",
                       container_id=container_id,
                       error=str(e))
            raise

    async def exec_run(
        self,
        container,
        command: Union[str, List[str]],
        **kwargs
    ) -> Any:
        """
        Execute command in container asynchronously.

        Args:
            container: Container object
            command: Command to execute
            **kwargs: Additional exec arguments

        Returns:
            Execution result
        """
        async with self._operation_semaphore:
            try:
                logger.debug("Executing command in container",
                           container_id=container.id[:12],
                           command=str(command)[:100])

                result = await asyncio.to_thread(
                    container.exec_run,
                    command,
                    **kwargs
                )

                logger.debug("Command executed successfully",
                           container_id=container.id[:12],
                           exit_code=result.exit_code)
                return result

            except Exception as e:
                logger.error("Failed to execute command",
                           container_id=container.id[:12],
                           command=str(command)[:100],
                           error=str(e))
                raise

    async def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Build Docker image asynchronously.

        Args:
            path: Build context path
            tag: Image tag
            dockerfile: Dockerfile path
            **kwargs: Additional build arguments

        Returns:
            Built image object
        """
        async with self._operation_semaphore:
            try:
                logger.info("Building Docker image async",
                          path=path,
                          tag=tag,
                          dockerfile=dockerfile)

                # Build operations can take a long time, use a higher timeout
                image, logs = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.docker_client.images.build,
                        path=path,
                        tag=tag,
                        dockerfile=dockerfile,
                        **kwargs
                    ),
                    timeout=self.timeout_config.docker_operation_timeout * 10  # 10x timeout for builds
                )

                logger.info("Docker image built successfully",
                          tag=tag,
                          image_id=image.id[:12])
                return image, logs

            except asyncio.TimeoutError:
                logger.error("Docker image build timed out",
                           tag=tag,
                           timeout=self.timeout_config.docker_operation_timeout * 10)
                raise
            except Exception as e:
                logger.error("Failed to build Docker image",
                           tag=tag,
                           error=str(e))
                raise

    async def get_image(self, image_name: str):
        """
        Get Docker image asynchronously.

        Args:
            image_name: Image name or ID

        Returns:
            Image object
        """
        try:
            image = await asyncio.to_thread(
                self.docker_client.images.get,
                image_name
            )
            return image
        except NotFound:
            logger.debug("Image not found",
                       image_name=image_name)
            raise
        except Exception as e:
            logger.error("Failed to get image",
                       image_name=image_name,
                       error=str(e))
            raise

    async def list_containers(self, **kwargs) -> List[Any]:
        """
        List containers asynchronously.

        Args:
            **kwargs: Filter arguments

        Returns:
            List of container objects
        """
        try:
            containers = await asyncio.to_thread(
                self.docker_client.containers.list,
                **kwargs
            )
            return containers
        except Exception as e:
            logger.error("Failed to list containers",
                       error=str(e))
            raise

    async def prune_containers(self) -> Dict[str, Any]:
        """
        Prune unused containers asynchronously.

        Returns:
            Pruning results
        """
        async with self._operation_semaphore:
            try:
                logger.info("Pruning unused containers")

                result = await asyncio.to_thread(
                    self.docker_client.containers.prune
                )

                logger.info("Container pruning completed",
                          containers_deleted=result.get('ContainersDeleted', 0),
                          space_reclaimed=result.get('SpaceReclaimed', 0))
                return result

            except Exception as e:
                logger.error("Failed to prune containers",
                           error=str(e))
                raise

    @asynccontextmanager
    async def container_lifecycle(
        self,
        image: str,
        command: Optional[Union[str, List[str]]] = None,
        auto_remove: bool = True,
        **kwargs
    ):
        """
        Async context manager for container lifecycle.

        Automatically creates, starts, and cleans up containers.

        Args:
            image: Docker image name
            command: Command to run
            auto_remove: Whether to remove container on exit
            **kwargs: Additional container creation arguments
        """
        container = None
        try:
            # Create container
            container = await self.create_container(
                image=image,
                command=command,
                detach=True,
                **kwargs
            )

            # Start container
            await self.start_container(container)

            yield container

        except Exception as e:
            logger.error("Container lifecycle error",
                       error=str(e),
                       container_id=container.id[:12] if container else "unknown")
            raise
        finally:
            if container:
                try:
                    # Stop container
                    await self.stop_container(container)

                    # Remove if requested
                    if auto_remove:
                        await self.remove_container(container)

                except Exception as cleanup_error:
                    logger.warning("Container cleanup failed",
                                 container_id=container.id[:12],
                                 error=str(cleanup_error))

    async def wait_for_container_ready(
        self,
        container,
        health_check_command: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        check_interval: float = 2.0
    ) -> bool:
        """
        Wait for container to be ready for operations.

        Args:
            container: Container object
            health_check_command: Command to check container health
            timeout: Maximum wait time
            check_interval: Time between checks

        Returns:
            True if container is ready, False if timeout
        """
        if timeout is None:
            timeout = self.timeout_config.container_startup_timeout

        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                # Reload container status
                await asyncio.to_thread(container.reload)

                if container.status != "running":
                    logger.debug("Container not running yet",
                               container_id=container.id[:12],
                               status=container.status)
                    await asyncio.sleep(check_interval)
                    continue

                # If health check command provided, run it
                if health_check_command:
                    result = await self.exec_run(
                        container,
                        health_check_command,
                        user="codex"
                    )

                    if result.exit_code == 0:
                        logger.debug("Container health check passed",
                                   container_id=container.id[:12])
                        return True
                    else:
                        logger.debug("Container health check failed",
                                   container_id=container.id[:12],
                                   exit_code=result.exit_code)
                else:
                    # No health check, just verify running status
                    logger.debug("Container is running",
                               container_id=container.id[:12])
                    return True

            except Exception as e:
                logger.debug("Container readiness check failed",
                           container_id=container.id[:12],
                           error=str(e))

            await asyncio.sleep(check_interval)

        logger.warning("Container readiness timeout",
                     container_id=container.id[:12],
                     timeout=timeout)
        return False