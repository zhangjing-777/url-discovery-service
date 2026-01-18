"""
定时任务管理路由
"""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models import DiscoveryTaskCreate, DiscoveryTaskUpdate, DiscoveryTaskResponse
from app.database import db
from app.crawler import URLDiscoveryCrawler
from app.call_url_audit_img import call_cds_url_audit


logger = logging.getLogger(__name__)

# 全局调度器变量,在main.py中设置
scheduler = None

def set_scheduler(s):
    """设置全局调度器实例"""
    global scheduler
    scheduler = s


router = APIRouter(prefix="/discovery-tasks", tags=["定时任务管理"])


@router.post("", response_model=DiscoveryTaskResponse)
async def create_discovery_task(task: DiscoveryTaskCreate, background_tasks: BackgroundTasks):
    """
    创建URL发现定时任务
    
    创建后会立即执行一次,然后按设定的间隔定时执行
    """
    try:
        # 检查任务名是否已存在
        check_sql = """
        SELECT id FROM url_discovery_tasks WHERE task_name = %s
        """
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(check_sql, (task.task_name,))
                existing = await cur.fetchone()
                
                if existing:
                    raise HTTPException(status_code=400, detail="任务名已存在")

                # 插入新任务
                next_time = datetime.now() + timedelta(seconds=task.execution_interval)
                
                insert_sql = """
                INSERT INTO url_discovery_tasks (
                    task_name, base_url, source_type, tags, depth,
                    strategy_type, strategy_contents, exclude_suffixes,
                    execution_interval, next_execution_time
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, task_name, base_url, source_type, tags, depth,
                          strategy_type, strategy_contents, exclude_suffixes,
                          execution_interval, next_execution_time, last_execution_time,
                          create_time, is_active, success_counts, fail_counts
                """
                
                await cur.execute(
                    insert_sql,
                    (
                        task.task_name,
                        str(task.base_url),
                        task.source_type,
                        task.tags,
                        task.depth,
                        task.strategy_type,
                        task.strategy_contents,
                        task.exclude_suffixes,
                        task.execution_interval,
                        next_time
                    )
                )
                
                result = await cur.fetchone()

        # 立即在后台执行一次
        if scheduler:
            background_tasks.add_task(
                scheduler.execute_task,
                task_id=result[0],
                task_name=result[1],
                base_url=result[2],
                source_type=result[3],
                tags=result[4],
                depth=result[5],
                strategy_type=result[6],
                strategy_contents=result[7],
                exclude_suffixes=result[8],
                execution_interval=result[9]
            )

        return DiscoveryTaskResponse(
            id=result[0],
            task_name=result[1],
            base_url=result[2],
            source_type=result[3],
            tags=result[4],
            depth=result[5],
            strategy_type=result[6],
            strategy_contents=result[7],
            exclude_suffixes=result[8],
            execution_interval=result[9],
            next_execution_time=result[10],
            last_execution_time=result[11],
            create_time=result[12],
            is_active=result[13],
            success_counts=result[14],
            fail_counts=result[15]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@router.get("", response_model=List[DiscoveryTaskResponse])
async def list_discovery_tasks(skip: int = 0, limit: int = 100):
    """获取任务列表"""
    try:
        sql = """
        SELECT id, task_name, base_url, source_type, tags, depth,
               strategy_type, strategy_contents, exclude_suffixes,
               execution_interval, next_execution_time, last_execution_time,
               create_time, is_active, success_counts, fail_counts
        FROM url_discovery_tasks
        ORDER BY create_time DESC
        OFFSET %s LIMIT %s
        """
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (skip, limit))
                results = await cur.fetchall()

        return [
            DiscoveryTaskResponse(
                id=row[0],
                task_name=row[1],
                base_url=row[2],
                source_type=row[3],
                tags=row[4],
                depth=row[5],
                strategy_type=row[6],
                strategy_contents=row[7],
                exclude_suffixes=row[8],
                execution_interval=row[9],
                next_execution_time=row[10],
                last_execution_time=row[11],
                create_time=row[12],
                is_active=row[13],
                success_counts=row[14],
                fail_counts=row[15]
            )
            for row in results
        ]

    except Exception as e:
        logger.error(f"查询任务列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{task_id}", response_model=DiscoveryTaskResponse)
async def get_discovery_task(task_id: int):
    """获取任务详情"""
    try:
        sql = """
        SELECT id, task_name, base_url, source_type, tags, depth,
               strategy_type, strategy_contents, exclude_suffixes,
               execution_interval, next_execution_time, last_execution_time,
               create_time, is_active, success_counts, fail_counts
        FROM url_discovery_tasks
        WHERE id = %s
        """
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (task_id,))
                result = await cur.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="任务不存在")

        return DiscoveryTaskResponse(
            id=result[0],
            task_name=result[1],
            base_url=result[2],
            source_type=result[3],
            tags=result[4],
            depth=result[5],
            strategy_type=result[6],
            strategy_contents=result[7],
            exclude_suffixes=result[8],
            execution_interval=result[9],
            next_execution_time=result[10],
            last_execution_time=result[11],
            create_time=result[12],
            is_active=result[13],
            success_counts=result[14],
            fail_counts=result[15]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.put("/{task_id}")
async def update_discovery_task(task_id: int, task_update: DiscoveryTaskUpdate):
    """更新任务配置"""
    try:
        # 检查任务是否存在
        check_sql = "SELECT task_name FROM url_discovery_tasks WHERE id = %s"
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(check_sql, (task_id,))
                existing = await cur.fetchone()
                
                if not existing:
                    raise HTTPException(status_code=404, detail="任务不存在")

                # 构建更新语句
                update_data = task_update.model_dump(exclude_unset=True)
                
                if not update_data:
                    return {"message": "没有需要更新的字段"}

                # 检查新任务名是否冲突
                if "task_name" in update_data:
                    await cur.execute(
                        "SELECT id FROM url_discovery_tasks WHERE task_name = %s AND id != %s",
                        (update_data["task_name"], task_id)
                    )
                    if await cur.fetchone():
                        raise HTTPException(status_code=400, detail="任务名已存在")

                # 构造动态SQL
                set_clauses = []
                values = []
                
                for field, value in update_data.items():
                    if field == "base_url":
                        value = str(value)
                    set_clauses.append(f"{field} = %s")
                    values.append(value)
                
                values.append(task_id)
                
                update_sql = f"""
                UPDATE url_discovery_tasks 
                SET {', '.join(set_clauses)}
                WHERE id = %s
                """
                
                await cur.execute(update_sql, tuple(values))

        return {"message": "任务更新成功", "updated_fields": list(update_data.keys())}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/{task_id}")
async def delete_discovery_task(task_id: int):
    """删除任务"""
    try:
        sql = "DELETE FROM url_discovery_tasks WHERE id = %s"
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (task_id,))
                
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="任务不存在")

        return {"message": "任务删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/{task_id}/stop")
async def stop_discovery_task(task_id: int):
    """停止任务"""
    try:
        sql = "UPDATE url_discovery_tasks SET is_active = FALSE WHERE id = %s"
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (task_id,))
                
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="任务不存在")

        return {"message": "任务已停止"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")


@router.post("/{task_id}/start")
async def start_discovery_task(task_id: int):
    """启动任务"""
    try:
        sql = """
        UPDATE url_discovery_tasks 
        SET is_active = TRUE, next_execution_time = NOW() 
        WHERE id = %s
        """
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (task_id,))
                
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="任务不存在")

        return {"message": "任务已启动"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")


@router.get("/{task_id}/status")
async def get_discovery_task_status(task_id: int):
    """获取任务运行状态"""
    try:
        sql = """
        SELECT task_name, is_active, success_counts, fail_counts,
               last_execution_time, next_execution_time
        FROM url_discovery_tasks
        WHERE id = %s
        """
        
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (task_id,))
                result = await cur.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="任务不存在")

        is_running = task_id in scheduler.running_tasks if scheduler else False

        return {
            "task_name": result[0],
            "is_active": result[1],
            "success_counts": result[2],
            "fail_counts": result[3],
            "last_execution_time": result[4],
            "next_execution_time": result[5],
            "is_running": is_running
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")